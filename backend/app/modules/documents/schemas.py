import uuid
from datetime import datetime

from pydantic import BaseModel, Field

class DocumentOut(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    file_url: str
    file_name: str
    file_type: str
    uploaded_by: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
