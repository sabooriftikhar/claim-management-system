"""
Users router.

  GET    /users/me           → any authenticated user
  GET    /users              → admin only  (paginated list)
  GET    /users/{id}         → admin only
  PATCH  /users/{id}/role    → admin only
  PATCH  /users/{id}/status  → admin only (activate / deactivate)
"""
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import get_current_user, require_role
from app.modules.users import service as user_svc
from app.modules.users.models import User
from app.modules.users.schemas import UserOut, UserUpdateRole, UsersListResponse
from app.shared.enums import UserRole
from app.shared.exceptions import ForbiddenError
from app.shared.schemas import MessageResponse

router = APIRouter()


# ── GET /users/me ─────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    summary="Get your own profile",
)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


# ── GET /users  (admin only) ──────────────────────────────────────────────────
@router.get(
    "",
    response_model=UsersListResponse,
    summary="List all users (admin only)",
)
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role([UserRole.admin])),
):
    users, total = await user_svc.get_all_users(db, limit=limit, offset=offset)
    return UsersListResponse(
        items=[UserOut.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── GET /users/{id}  (admin only) ─────────────────────────────────────────────
@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get a user by ID (admin only)",
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role([UserRole.admin])),
):
    user = await user_svc.get_user_by_id(db, user_id)
    return UserOut.model_validate(user)


# ── PATCH /users/{id}/role  (admin only) ──────────────────────────────────────
@router.patch(
    "/{user_id}/role",
    response_model=UserOut,
    summary="Update a user's role (admin only)",
)
async def update_role(
    user_id: uuid.UUID,
    body: UserUpdateRole,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role([UserRole.admin])),
):
    # Prevent admin from accidentally demoting themselves
    if user_id == admin.id:
        raise ForbiddenError("You cannot change your own role.")
    user = await user_svc.update_user_role(db, user_id, body.role)
    return UserOut.model_validate(user)


# ── PATCH /users/{id}/status  (admin only) ────────────────────────────────────
@router.patch(
    "/{user_id}/status",
    response_model=UserOut,
    summary="Activate or deactivate a user (admin only)",
)
async def update_status(
    user_id: uuid.UUID,
    is_active: bool,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role([UserRole.admin])),
):
    if user_id == admin.id:
        raise ForbiddenError("You cannot deactivate your own account.")
    user = await user_svc.get_user_by_id(db, user_id)
    user.is_active = is_active
    db.add(user)
    return UserOut.model_validate(user)
