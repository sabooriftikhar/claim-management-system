"""
Pydantic schemas for the users module.
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.shared.enums import UserRole


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRole(BaseModel):
    role: UserRole


class UsersListResponse(BaseModel):
    items: list[UserOut]
    total: int
    limit: int
    offset: int
