import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user, require_role
from app.modules.users.models import User
from app.modules.users.schemas import UserOut
from app.shared.enums import UserRole
from app.shared.schemas import MessageResponse

from app.modules.admin.schemas import AnalyticsSummaryOut, UserRoleUpdate
from app.modules.admin import service

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_role([UserRole.admin]))]
)

@router.get("/analytics/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get high-level statistics of claims for the admin dashboard."""
    return await service.get_analytics_summary(db)

@router.get("/users", response_model=List[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all registered users."""
    users = await service.list_users(db)
    return [UserOut.model_validate(u) for u in users]

@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the role of a user."""
    updated_user = await service.update_user_role(db, user_id, body.role)
    return UserOut.model_validate(updated_user)
