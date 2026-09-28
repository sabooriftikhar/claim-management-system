import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    message: str
    link_url: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
