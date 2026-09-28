"""
Auth service — all business logic for register / login / refresh / logout.

Design decisions worth knowing:
- Refresh tokens are stored HASHED in the DB (SHA-256 of the raw JWT).
  If the DB is leaked, an attacker can't replay the tokens.
- On refresh, the old token is revoked and a new one issued (rotation).
  This means a stolen refresh token can only be used once before it's dead.
- Logout deletes the token record, making revocation immediate.
- get_current_user loads the full ORM User so downstream code has the real object.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.modules.auth.schemas import RegisterRequest, TokenResponse, AccessTokenResponse
from app.modules.users.models import RefreshToken, User
from app.shared.enums import UserRole
from app.shared.exceptions import ConflictError, UnauthorizedError

bearer_scheme = HTTPBearer(auto_error=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw JWT string."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ── Core auth operations ──────────────────────────────────────────────────────

_BOOTSTRAP_ADMIN_EMAIL = "abdulsabooriftikhar3718@gmail.com"


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    existing = await _get_user_by_email(db, data.email)
    if existing:
        raise ConflictError("An account with this email already exists.")

    # Bootstrap admin email always gets admin role, regardless of chosen role.
    # All other users get the role they selected (claimant or adjuster).
    if data.email.lower() == _BOOTSTRAP_ADMIN_EMAIL:
        assigned_role = UserRole.admin
    else:
        assigned_role = UserRole(data.role)

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=assigned_role,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # get the id without committing yet
    return user


async def login_user(db: AsyncSession, email: str, password: str) -> tuple[User, str, str]:
    """
    Returns (user, access_token, refresh_token) on success.
    Raises 401 on bad credentials or inactive account.
    """
    user = await _get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Incorrect email or password.")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled.")

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )
    raw_refresh = create_refresh_token(subject=str(user.id))

    # Persist hashed refresh token
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    rt = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(raw_refresh),
        expires_at=expires_at,
    )
    db.add(rt)
    await db.flush()

    return user, access_token, raw_refresh


async def refresh_tokens(db: AsyncSession, raw_refresh: str) -> tuple[str, str]:
    """
    Validates the refresh token, rotates it, returns (new_access, new_refresh).
    Raises 401 if the token is invalid, expired, or already revoked.
    """
    payload = decode_refresh_token(raw_refresh)
    if not payload:
        raise UnauthorizedError("Invalid or expired refresh token.")

    token_hash = _hash_token(raw_refresh)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise UnauthorizedError("Refresh token not found or already revoked.")

    if stored.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token has expired.")

    user = await _get_user_by_id(db, stored.user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")

    # Revoke old token (rotation)
    stored.revoked = True
    db.add(stored)

    # Issue new pair
    new_access = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )
    new_raw_refresh = create_refresh_token(subject=str(user.id))
    new_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(new_raw_refresh),
        expires_at=new_expires,
    )
    db.add(new_rt)
    await db.flush()

    return new_access, new_raw_refresh


async def logout_user(db: AsyncSession, raw_refresh: str) -> None:
    """Revokes the refresh token. Idempotent — no error if already gone."""
    token_hash = _hash_token(raw_refresh)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        db.add(stored)


# ── FastAPI dependency: get_current_user ──────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decodes the Bearer JWT and loads the full User ORM object from DB.
    FastAPI deduplicates dependencies — if an endpoint also has get_db(),
    the SAME session instance is reused (no second connection opened).
    """
    from app.core.security import decode_access_token

    if not credentials:
        raise UnauthorizedError()

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise UnauthorizedError("Invalid or expired token.")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedError("Malformed token.")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise UnauthorizedError("Malformed token.")

    user = await _get_user_by_id(db, user_id)
    if not user:
        raise UnauthorizedError("User not found.")
    if not user.is_active:
        raise UnauthorizedError("Account is disabled.")

    return user


def require_role(allowed_roles: list[UserRole]):
    """
    Dependency factory that gates an endpoint to specific roles.
    Depends on get_current_user — FastAPI deduplicates get_db() so only
    ONE DB session (and one connection) is used per request.
    Usage: current_user: User = Depends(require_role([UserRole.admin]))
    """
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            from app.shared.exceptions import ForbiddenError
            raise ForbiddenError(
                f"Required role(s): {[r.value for r in allowed_roles]}. "
                f"Your role: {user.role.value}"
            )
        return user
    return _check
