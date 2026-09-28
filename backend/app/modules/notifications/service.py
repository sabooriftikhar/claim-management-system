import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.users.models import User
from app.shared.exceptions import ForbiddenError, NotFoundError

async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    message: str,
    link_url: str | None = None
) -> Notification:
    """Create a new notification for a user."""
    notif = Notification(
        user_id=user_id,
        message=message,
        link_url=link_url,
        is_read=False,
    )
    db.add(notif)
    # Note: caller is usually responsible for calling commit/flush, 
    # but we can flush here to assign ID if needed.
    # No flush needed if we just attach it to the session.
    return notif

async def get_unread_notifications(
    db: AsyncSession,
    actor: User
) -> list[Notification]:
    """Get all unread notifications for a user."""
    q = select(Notification).where(
        Notification.user_id == actor.id,
        Notification.is_read == False
    ).order_by(Notification.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())

async def mark_as_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    actor: User
) -> Notification:
    """Mark a notification as read. Enforces ownership."""
    q = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(q)
    notif = result.scalar_one_or_none()
    
    if not notif:
        raise NotFoundError("Notification")
        
    if notif.user_id != actor.id:
        raise ForbiddenError("You can only update your own notifications.")
        
    notif.is_read = True
    db.add(notif)
    await db.flush()
    return notif
