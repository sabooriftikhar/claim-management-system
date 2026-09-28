"""
Claims router — all endpoints under /claims.

POST   /claims                  create a new claim (claimant/admin)
GET    /claims                  role-scoped list
GET    /claims/{id}             detail + history (ownership enforced)
PATCH  /claims/{id}             edit while draft/submitted (claimant/admin)
DELETE /claims/{id}             soft-delete (claimant own draft, or admin)
POST   /claims/{id}/submit      draft → submitted
POST   /claims/{id}/assign      submitted → in_review + set assignee
GET    /claims/{id}/history     full status audit trail
GET    /claims/types            list valid claim_type values
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user, require_role
from app.modules.claims import service as claims_svc
from app.modules.claims.schemas import (
    ClaimAssign,
    ClaimCreate,
    ClaimDetail,
    ClaimOut,
    ClaimsListResponse,
    ClaimUpdate,
    StatusHistoryEntry,
    CLAIM_TYPES,
)
from app.modules.users.models import User
from app.shared.enums import ClaimStatus, UserRole
from app.shared.schemas import MessageResponse

router = APIRouter()


# ── GET /claims/types  ────────────────────────────────────────────────────────
@router.get(
    "/types",
    response_model=list[str],
    summary="List valid claim types",
)
async def list_claim_types():
    """Returns the allowed claim_type values. No auth required."""
    return CLAIM_TYPES


# ── POST /claims  ─────────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=ClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="File a new claim",
)
async def create_claim(
    body: ClaimCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Any authenticated user can file a claim (created as DRAFT).
    In practice claimants file their own; admins may file on behalf.
    """
    claim = await claims_svc.create_claim(db, body, current_user)
    return ClaimOut.model_validate(claim)


# ── GET /claims  ──────────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=ClaimsListResponse,
    summary="List claims (role-scoped)",
)
async def list_claims(
    status: Optional[ClaimStatus] = Query(default=None, description="Filter by status"),
    assigned: Optional[str] = Query(default=None, description="Filter by assignment: 'me' or 'unassigned'"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claims, total = await claims_svc.list_claims(
        db, current_user, status_filter=status, assigned_filter=assigned, limit=limit, offset=offset
    )
    return ClaimsListResponse(
        items=[ClaimOut.model_validate(c) for c in claims],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── GET /claims/{id}  ─────────────────────────────────────────────────────────
@router.get(
    "/{claim_id}",
    response_model=ClaimDetail,
    summary="Get claim detail with status history",
)
async def get_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = await claims_svc.get_claim(db, claim_id, current_user)
    history = [StatusHistoryEntry.model_validate(h) for h in claim.status_history]
    detail = ClaimDetail.model_validate(claim)
    detail.status_history = history
    return detail


# ── PATCH /claims/{id}  ───────────────────────────────────────────────────────
@router.patch(
    "/{claim_id}",
    response_model=ClaimOut,
    summary="Edit a claim (draft/submitted only)",
)
async def update_claim(
    claim_id: uuid.UUID,
    body: ClaimUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = await claims_svc.update_claim(db, claim_id, body, current_user)
    return ClaimOut.model_validate(claim)


# ── DELETE /claims/{id}  ──────────────────────────────────────────────────────
@router.delete(
    "/{claim_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a claim",
)
async def delete_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await claims_svc.delete_claim(db, claim_id, current_user)


# ── POST /claims/{id}/submit  ─────────────────────────────────────────────────
@router.post(
    "/{claim_id}/submit",
    response_model=ClaimOut,
    summary="Submit a draft claim for review",
)
async def submit_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    claim = await claims_svc.submit_claim(db, claim_id, current_user)
    return ClaimOut.model_validate(claim)


# ── POST /claims/{id}/assign  ─────────────────────────────────────────────────
@router.post(
    "/{claim_id}/assign",
    response_model=ClaimOut,
    summary="Assign claim to an adjuster (moves to in_review)",
)
async def assign_claim(
    claim_id: uuid.UUID,
    body: ClaimAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.adjuster, UserRole.admin])
    ),
):
    claim = await claims_svc.assign_claim(
        db, claim_id, body.adjuster_id, current_user
    )
    return ClaimOut.model_validate(claim)


@router.post(
    "/{claim_id}/settle",
    response_model=ClaimOut,
    summary="Record settlement for an approved claim",
)
async def settle_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.adjuster, UserRole.admin])
    ),
):
    claim = await claims_svc.settle_claim(db, claim_id, current_user)
    return ClaimOut.model_validate(claim)


@router.post(
    "/{claim_id}/close",
    response_model=ClaimOut,
    summary="Close a settled or rejected claim",
)
async def close_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(
        require_role([UserRole.adjuster, UserRole.admin])
    ),
):
    claim = await claims_svc.close_claim(db, claim_id, current_user)
    return ClaimOut.model_validate(claim)


# ── GET /claims/{id}/history  ─────────────────────────────────────────────────
@router.get(
    "/{claim_id}/history",
    response_model=list[StatusHistoryEntry],
    summary="Full status audit trail for a claim",
)
async def get_claim_history(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    history = await claims_svc.get_claim_history(db, claim_id, current_user)
    return [StatusHistoryEntry.model_validate(h) for h in history]
