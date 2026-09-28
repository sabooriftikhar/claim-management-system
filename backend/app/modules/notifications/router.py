import uuid

from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user
from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationOut
from app.modules.users.models import User
from app.shared.schemas import MessageResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=list[NotificationOut])
async def get_unread_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all unread notifications for the authenticated user."""
    return await service.get_unread_notifications(db, current_user)

@router.patch("/{id}/read", response_model=MessageResponse)
async def mark_notification_as_read(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a specific notification as read."""
    await service.mark_as_read(db, id, current_user)
    return {"message": "Notification marked as read"}
