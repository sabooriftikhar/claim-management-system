import uuid
from typing import Dict, Any, List, Tuple
from sqlalchemy import select, func, cast, Float
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.modules.claims.models import Claim, ClaimStatusHistory
from app.modules.users.models import User
from app.modules.admin.schemas import AnalyticsSummaryOut
from app.shared.enums import ClaimStatus, UserRole
from app.shared.exceptions import NotFoundError

async def get_analytics_summary(db: AsyncSession) -> AnalyticsSummaryOut:
    # 1. Total claims
    total_q = select(func.count(Claim.id)).where(Claim.is_deleted == False)
    total_result = await db.execute(total_q)
    total_claims = total_result.scalar_one()

    # 2. Claims by status
    status_q = select(Claim.status, func.count(Claim.id)).where(Claim.is_deleted == False).group_by(Claim.status)
    status_result = await db.execute(status_q)
    claims_by_status = {status.value: count for status, count in status_result.all()}

    # 3. Average resolution time (days)
    # Average time between claim created (from_status=None) and terminal status (approved/rejected/closed)
    # We can approximate by looking at the diff between created_at and updated_at for terminal claims
    avg_q = select(
        func.avg(
            func.extract('epoch', Claim.updated_at) - func.extract('epoch', Claim.created_at)
        )
    ).where(
        Claim.is_deleted == False,
        Claim.status.in_([ClaimStatus.approved, ClaimStatus.rejected, ClaimStatus.closed])
    )
    avg_result = await db.execute(avg_q)
    avg_seconds = avg_result.scalar_one_or_none()
    avg_days = (avg_seconds / 86400.0) if avg_seconds else None

    return AnalyticsSummaryOut(
        total_claims=total_claims,
        claims_by_status=claims_by_status,
        avg_resolution_time_days=avg_days
    )

async def list_users(db: AsyncSession) -> List[User]:
    q = select(User).order_by(User.created_at.desc())
    result = await db.execute(q)
    return list(result.scalars().all())

async def update_user_role(db: AsyncSession, user_id: uuid.UUID, new_role: UserRole) -> User:
    q = select(User).where(User.id == user_id)
    result = await db.execute(q)
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User")
    
    user.role = new_role
    db.add(user)
    await db.flush()
    return user
