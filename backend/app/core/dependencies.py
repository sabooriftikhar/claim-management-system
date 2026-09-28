"""
Shared FastAPI dependencies — current user extraction and RBAC guards.
Stubs in Phase 0; fully wired in Phase 1 when the users table exists.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List

from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    Decodes the Bearer JWT and returns the raw payload.
    Phase 1 will replace this with a version that loads the full User ORM object.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_role(allowed_roles: List[str]):
    """
    Dependency factory — gates an endpoint to specific roles.
    Usage:  Depends(require_role(["admin", "adjuster"]))
    """
    async def _check(payload: dict = Depends(get_current_user_payload)):
        role = payload.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}",
            )
        return payload
    return _check
