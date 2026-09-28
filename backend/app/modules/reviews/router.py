import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user, require_role
from app.modules.reviews import service as reviews_svc
from app.modules.reviews.schemas import ReviewCreate, ReviewOut
from app.modules.users.models import User
from app.shared.enums import UserRole

router = APIRouter()

@router.post(
    "/{claim_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a review decision for a claim",
)
async def submit_review(
    claim_id: uuid.UUID,
    body: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.adjuster, UserRole.admin])),
):
    review = await reviews_svc.create_review(db, claim_id, body, current_user)
    return ReviewOut.model_validate(review)
