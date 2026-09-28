import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.shared.enums import ReviewDecision


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    comments: str = Field(..., min_length=1)
    approved_amount: Optional[float] = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: ReviewDecision
    comments: str
    created_at: datetime

    class Config:
        from_attributes = True
