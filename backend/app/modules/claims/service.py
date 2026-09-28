"""
Claims service — all business logic for the claims module.

Key design decisions:
- State machine enforced HERE, not in the router. Illegal transitions raise 409.
- Every status change writes an append-only ClaimStatusHistory row — no exceptions.
- Role-scoped listing: claimants see only their own, adjusters see assigned+unassigned,
  admins see everything. This is ownership-based auth on top of RBAC.
- Soft-delete only: claims are never hard-deleted (audit trail must survive).
- All mutations flush (not commit) — the get_db() dependency commits on success.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.claims.models import Claim, ClaimStatusHistory
from app.modules.claims.schemas import ClaimCreate, ClaimUpdate
from app.modules.notifications.service import create_notification
from app.modules.users.models import User
from app.shared.enums import ClaimStatus, UserRole, is_valid_transition
from app.shared.exceptions import (
    ConflictError,
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_claim_or_404(
    db: AsyncSession, claim_id: uuid.UUID, load_history: bool = False
) -> Claim:
    """Fetch a non-deleted claim by id, optionally eager-loading status history."""
    q = select(Claim).where(Claim.id == claim_id, Claim.is_deleted == False)  # noqa: E712
    if load_history:
        q = q.options(selectinload(Claim.status_history))
    result = await db.execute(q)
    claim = result.scalar_one_or_none()
    if not claim:
        raise NotFoundError("Claim")
    return claim


def _assert_ownership_or_role(claim: Claim, actor: User) -> None:
    """
    Row-level authorization check.
    - Claimant: must own the claim.
    - Adjuster: must be assigned to the claim (or claim is unassigned for self-assign).
    - Admin: always allowed.
    """
    if actor.role == UserRole.admin:
        return
    if actor.role == UserRole.claimant and claim.claimant_id != actor.id:
        raise ForbiddenError("You can only access your own claims.")
    if actor.role == UserRole.adjuster and claim.assigned_to not in (actor.id, None):
        raise ForbiddenError("This claim is assigned to a different adjuster.")


def _record_transition(
    db: AsyncSession,
    claim: Claim,
    to_status: ClaimStatus,
    actor: User,
    note: str | None = None,
) -> ClaimStatusHistory:
    """
    Apply a status transition to the claim and write the history entry.
    Validates the transition — raises 409 on illegal moves.
    """
    if claim.status != to_status:
        if not is_valid_transition(claim.status, to_status):
            raise InvalidTransitionError(claim.status.value, to_status.value)

    entry = ClaimStatusHistory(
        claim_id=claim.id,
        from_status=claim.status,
        to_status=to_status,
        changed_by=actor.id,
        note=note,
    )
    claim.status = to_status
    db.add(entry)
    db.add(claim)

    # Create a notification for the claimant if someone else is updating the status
    if actor.id != claim.claimant_id:
        msg = f"Your claim {claim.claim_type.replace('_', ' ').capitalize()} update: status changed to {to_status.value.replace('_', ' ').capitalize()}."
        # Local import to avoid circular dependency
        from app.modules.notifications.models import Notification
        notif = Notification(
            user_id=claim.claimant_id,
            message=msg,
            link_url=f"/claims/{claim.id}",
        )
        db.add(notif)

    return entry


# ── Create ────────────────────────────────────────────────────────────────────

async def create_claim(
    db: AsyncSession, data: ClaimCreate, actor: User
) -> Claim:
    """
    Creates a claim in DRAFT status and records the initial history entry.
    Only claimants (and admins filing on behalf) can create claims.
    """
    claim = Claim(
        claimant_id=actor.id,
        claim_type=data.claim_type,
        description=data.description,
        claimed_amount=float(data.claimed_amount),
        incident_date=data.incident_date,
        status=ClaimStatus.draft,
    )
    db.add(claim)
    await db.flush()  # get the id

    # Initial history entry (from_status=None means "created")
    entry = ClaimStatusHistory(
        claim_id=claim.id,
        from_status=None,
        to_status=ClaimStatus.draft,
        changed_by=actor.id,
        note="Claim created.",
    )
    db.add(entry)
    await db.flush()
    return claim


# ── Read ──────────────────────────────────────────────────────────────────────

async def get_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> Claim:
    """Fetch single claim with status history. Enforces ownership."""
    claim = await _get_claim_or_404(db, claim_id, load_history=True)
    _assert_ownership_or_role(claim, actor)
    return claim


async def list_claims(
    db: AsyncSession,
    actor: User,
    status_filter: ClaimStatus | None = None,
    assigned_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Claim], int]:
    """
    Role-scoped listing:
      claimant → own claims only
      adjuster → claims assigned to them OR unassigned
      admin    → all claims
    """
    base = select(Claim).where(Claim.is_deleted == False)  # noqa: E712

    if actor.role == UserRole.claimant:
        base = base.where(Claim.claimant_id == actor.id)
    elif actor.role == UserRole.adjuster:
        base = base.where(
            or_(Claim.assigned_to == actor.id, Claim.assigned_to.is_(None))
        )
    # admin: no additional filter

    if assigned_filter == "me":
        base = base.where(Claim.assigned_to == actor.id)
    elif assigned_filter == "unassigned":
        base = base.where(Claim.assigned_to.is_(None))

    if status_filter:
        base = base.where(Claim.status == status_filter)

    count_q = select(func.count()).select_from(base.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    claims_q = (
        base.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
    )
    result = await db.execute(claims_q)
    claims = list(result.scalars().all())
    return claims, total


# ── Update ────────────────────────────────────────────────────────────────────

async def update_claim(
    db: AsyncSession, claim_id: uuid.UUID, data: ClaimUpdate, actor: User
) -> Claim:
    """
    Claimants may edit their own claim only while draft or submitted.
    Admins may edit at any non-terminal status.
    """
    claim = await _get_claim_or_404(db, claim_id)
    _assert_ownership_or_role(claim, actor)

    # Claimants: editable only in early states
    if actor.role == UserRole.claimant and claim.status not in (
        ClaimStatus.draft, ClaimStatus.submitted
    ):
        raise ForbiddenError(
            "Claims can only be edited while in draft or submitted status."
        )

    if data.claim_type is not None:
        claim.claim_type = data.claim_type
    if data.description is not None:
        claim.description = data.description
    if data.claimed_amount is not None:
        claim.claimed_amount = float(data.claimed_amount)
    if data.incident_date is not None:
        claim.incident_date = data.incident_date

    claim.updated_at = datetime.now(timezone.utc)
    db.add(claim)
    await db.flush()
    return claim


# ── Submit ────────────────────────────────────────────────────────────────────

async def submit_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> Claim:
    """Transition draft → submitted. Only the claimant (or admin) can submit."""
    claim = await _get_claim_or_404(db, claim_id)

    if actor.role == UserRole.claimant and claim.claimant_id != actor.id:
        raise ForbiddenError("You can only submit your own claims.")

    _record_transition(
        db, claim, ClaimStatus.submitted, actor, note="Submitted for review."
    )
    await db.flush()
    return claim


# ── Assign ────────────────────────────────────────────────────────────────────

async def assign_claim(
    db: AsyncSession,
    claim_id: uuid.UUID,
    adjuster_id: uuid.UUID,
    actor: User,
) -> Claim:
    """
    Assign a submitted claim to an adjuster.
    Allowed by: admin (any adjuster) or the adjuster themselves (self-assign).
    Triggers submitted → in_review transition.
    """
    claim = await _get_claim_or_404(db, claim_id)

    if actor.role == UserRole.adjuster and adjuster_id != actor.id:
        raise ForbiddenError("Adjusters can only self-assign claims.")

    # Verify the target user exists and is an adjuster
    from sqlalchemy import select as sa_select
    from app.modules.users.models import User as UserModel
    result = await db.execute(
        sa_select(UserModel).where(
            UserModel.id == adjuster_id,
            UserModel.role == UserRole.adjuster,
            UserModel.is_active == True,  # noqa: E712
        )
    )
    adjuster = result.scalar_one_or_none()
    if not adjuster:
        raise NotFoundError("Adjuster user")

    claim.assigned_to = adjuster_id
    _record_transition(
        db, claim, ClaimStatus.in_review, actor,
        note=f"Assigned to adjuster {adjuster.full_name}."
    )
    await db.flush()
    return claim


async def settle_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> Claim:
    """Move an approved claim to settled after the mocked resolution step."""
    claim = await _get_claim_or_404(db, claim_id)
    _assert_ownership_or_role(claim, actor)
    if actor.role == UserRole.adjuster and claim.assigned_to != actor.id:
        raise ForbiddenError("Only the assigned adjuster can settle this claim.")
    if actor.role == UserRole.claimant:
        raise ForbiddenError("Only an assigned adjuster or admin can settle a claim.")
    _record_transition(
        db, claim, ClaimStatus.settled, actor, note="Claim settlement recorded."
    )
    await db.flush()
    return claim


async def close_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> Claim:
    """Close a settled or rejected claim and preserve the audit entry."""
    claim = await _get_claim_or_404(db, claim_id)
    _assert_ownership_or_role(claim, actor)
    if actor.role == UserRole.adjuster and claim.assigned_to != actor.id:
        raise ForbiddenError("Only the assigned adjuster can close this claim.")
    if actor.role == UserRole.claimant:
        raise ForbiddenError("Only an assigned adjuster or admin can close a claim.")
    _record_transition(
        db, claim, ClaimStatus.closed, actor, note="Claim closed."
    )
    await db.flush()
    return claim


# ── Delete (soft) ─────────────────────────────────────────────────────────────

async def delete_claim(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> None:
    """
    Soft-delete. Only admins and the owning claimant (while draft) can delete.
    """
    claim = await _get_claim_or_404(db, claim_id)

    if actor.role == UserRole.claimant:
        if claim.claimant_id != actor.id:
            raise ForbiddenError("You can only delete your own claims.")
        if claim.status != ClaimStatus.draft:
            raise ForbiddenError("Only draft claims can be deleted.")

    claim.is_deleted = True
    db.add(claim)
    await db.flush()


# ── Status history ────────────────────────────────────────────────────────────

async def get_claim_history(
    db: AsyncSession, claim_id: uuid.UUID, actor: User
) -> list[ClaimStatusHistory]:
    """Return the full audit trail for a claim."""
    claim = await _get_claim_or_404(db, claim_id, load_history=True)
    _assert_ownership_or_role(claim, actor)
    return claim.status_history
