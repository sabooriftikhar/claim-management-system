"""
Common Pydantic response shapes used across the API.
"""
from pydantic import BaseModel
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list wrapper."""
    items: List[T]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Simple message/confirmation response."""
    message: str


class ErrorDetail(BaseModel):
    """Structured error body."""
    detail: str
    code: Optional[str] = None
