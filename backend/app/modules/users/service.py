"""
Users service — profile reads and admin role management.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.shared.enums import UserRole
from app.shared.exceptions import NotFoundError


async def get_all_users(
    db: AsyncSession, limit: int = 20, offset: int = 0
) -> tuple[list[User], int]:
    count_result = await db.execute(select(func.count()).select_from(User))
    total = count_result.scalar_one()

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    users = list(result.scalars().all())
    return users, total


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User")
    return user


async def update_user_role(db: AsyncSession, user_id: uuid.UUID, new_role: UserRole) -> User:
    user = await get_user_by_id(db, user_id)
    user.role = new_role
    db.add(user)
    await db.flush()
    return user
