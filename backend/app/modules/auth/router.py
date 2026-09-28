"""
Auth router — public endpoints (no auth required except logout/refresh).

Cookie strategy:
  - The refresh token is set as an httpOnly, Secure, SameSite=Lax cookie
    by the backend so JavaScript can never read it (XSS protection).
  - The access token is returned in the JSON body; the frontend stores it
    in memory (React context) only — never localStorage.
  - The cookie name is "refresh_token".

Rate limiting:
  - /login and /register are limited to 10 requests/minute per IP.
    This makes brute-force attacks 10× slower without blocking legitimate use.
"""
from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.main import limiter
from app.modules.auth import service as auth_svc
from app.modules.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import get_current_user
from app.modules.users.models import User
from app.modules.users.schemas import UserOut
from app.shared.schemas import MessageResponse

router = APIRouter()

_COOKIE_NAME = "refresh_token"
_COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # seconds


def _set_refresh_cookie(response: Response, raw_refresh: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,          # JS cannot read this
        secure=settings.APP_ENV != "development",  # HTTPS only in prod
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_COOKIE_NAME, path="/")


# ── POST /auth/register ───────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
@limiter.limit("10/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user = await auth_svc.register_user(db, body)
    # Log the new user in immediately after registration
    user, access_token, raw_refresh = await auth_svc.login_user(db, body.email, body.password)
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user))


# ── POST /auth/login ──────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive tokens",
)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    user, access_token, raw_refresh = await auth_svc.login_user(db, body.email, body.password)
    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=access_token, user=UserOut.model_validate(user))


# ── POST /auth/refresh ────────────────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Rotate refresh token and get a new access token",
)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
):
    """
    Reads the refresh token from the httpOnly cookie.
    Rotates it (old token revoked, new one issued) and returns a new access token.
    """
    if not refresh_token:
        from app.shared.exceptions import UnauthorizedError
        raise UnauthorizedError("No refresh token cookie found.")

    new_access, new_raw_refresh = await auth_svc.refresh_tokens(db, refresh_token)
    _set_refresh_cookie(response, new_raw_refresh)
    return AccessTokenResponse(access_token=new_access)


# ── POST /auth/logout ─────────────────────────────────────────────────────────
@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke refresh token and clear session",
)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    _current_user: User = Depends(get_current_user),
):
    """
    Requires a valid access token (proves who is logging out).
    Revokes the refresh token from the DB and clears the cookie.
    """
    if refresh_token:
        await auth_svc.logout_user(db, refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out successfully.")


# ── GET /auth/me (convenience alias) ─────────────────────────────────────────
@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current authenticated user (quick alias)",
)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
