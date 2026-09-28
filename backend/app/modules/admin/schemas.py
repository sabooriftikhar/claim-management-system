import uuid
from pydantic import BaseModel
from typing import Dict, Any

from app.shared.enums import UserRole

class AnalyticsSummaryOut(BaseModel):
    total_claims: int
    claims_by_status: Dict[str, int]
    avg_resolution_time_days: float | None

class UserRoleUpdate(BaseModel):
    role: UserRole
