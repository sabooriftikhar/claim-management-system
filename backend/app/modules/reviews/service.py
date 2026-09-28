import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.reviews.models import ClaimReview
from app.modules.reviews.schemas import ReviewCreate
from app.modules.users.models import User
from app.shared.enums import ClaimStatus, ReviewDecision, UserRole
from app.shared.exceptions import ForbiddenError, ConflictError
from app.modules.claims.service import _get_claim_or_404, _record_transition

async def create_review(
    db: AsyncSession,
    claim_id: uuid.UUID,
    data: ReviewCreate,
    actor: User,
) -> ClaimReview:
    claim = await _get_claim_or_404(db, claim_id)

    if actor.role == UserRole.adjuster and claim.assigned_to != actor.id:
        raise ForbiddenError("You can only review claims assigned to you.")

    if claim.status != ClaimStatus.in_review:
        raise ConflictError("Only claims in 'in_review' status can be reviewed.")

    if data.decision == ReviewDecision.approve and (data.approved_amount is None or data.approved_amount <= 0):
        raise ConflictError("Approved claims must have a valid approved_amount.")

    review = ClaimReview(
        claim_id=claim.id,
        reviewer_id=actor.id,
        decision=data.decision,
        comments=data.comments,
    )
    db.add(review)

    # Process status transition
    note = f"Review decision: {data.decision.value.upper()}. Comments: {data.comments}"
    
    if data.decision == ReviewDecision.approve:
        claim.approved_amount = data.approved_amount
        _record_transition(db, claim, ClaimStatus.approved, actor, note=note)
    elif data.decision == ReviewDecision.reject:
        _record_transition(db, claim, ClaimStatus.rejected, actor, note=note)
    elif data.decision == ReviewDecision.request_info:
        # Keep it in in_review, but write a history entry
        _record_transition(db, claim, ClaimStatus.in_review, actor, note=note)

    await db.flush()
    return review
