"""
Pydantic schemas for the claims module.
Input schemas validate what the client sends.
Output schemas control exactly what we return — never expose internal fields.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.shared.enums import ClaimStatus


# ── Claim Types (domain vocabulary) ──────────────────────────────────────────
CLAIM_TYPES = [
    "warranty",
    "defect",
    "damaged_shipment",
    "expense_reimbursement",
    "other",
]


# ── Input schemas ─────────────────────────────────────────────────────────────

class ClaimCreate(BaseModel):
    claim_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10, max_length=5000)
    claimed_amount: Decimal = Field(gt=0, le=1_000_000, decimal_places=2)
    incident_date: datetime

    @field_validator("claim_type")
    @classmethod
    def validate_claim_type(cls, v: str) -> str:
        if v not in CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of: {CLAIM_TYPES}")
        return v


class ClaimUpdate(BaseModel):
    """Claimant may only edit a claim while it is draft or submitted."""
    claim_type: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, min_length=10, max_length=5000)
    claimed_amount: Optional[Decimal] = Field(default=None, gt=0, le=1_000_000, decimal_places=2)
    incident_date: Optional[datetime] = None

    @field_validator("claim_type")
    @classmethod
    def validate_claim_type(cls, v: str | None) -> str | None:
        if v is not None and v not in CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of: {CLAIM_TYPES}")
        return v


class ClaimAssign(BaseModel):
    """Admin/adjuster assigns the claim to an adjuster."""
    adjuster_id: uuid.UUID


# ── Output schemas ────────────────────────────────────────────────────────────

class StatusHistoryEntry(BaseModel):
    id: uuid.UUID
    from_status: Optional[ClaimStatus]
    to_status: ClaimStatus
    changed_by: uuid.UUID
    note: Optional[str]
    changed_at: datetime

    model_config = {"from_attributes": True}


class ClaimOut(BaseModel):
    id: uuid.UUID
    claimant_id: uuid.UUID
    assigned_to: Optional[uuid.UUID]
    claim_type: str
    description: str
    claimed_amount: Decimal
    approved_amount: Optional[Decimal]
    status: ClaimStatus
    incident_date: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClaimDetail(ClaimOut):
    """Full claim with audit trail — used on the detail page."""
    status_history: list[StatusHistoryEntry] = []


class ClaimsListResponse(BaseModel):
    items: list[ClaimOut]
    total: int
    limit: int
    offset: int
