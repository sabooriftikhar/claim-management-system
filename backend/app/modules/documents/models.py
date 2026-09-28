import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

class ClaimDocument(Base):
    __tablename__ = "claim_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False, index=True)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def file_url(self) -> str:
        return f"/claims/{self.claim_id}/documents/{self.id}/download"

