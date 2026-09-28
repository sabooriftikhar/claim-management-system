"""
ORM models for the claims module.

  Claim             : core claim record with state machine status
  ClaimStatusHistory: append-only audit table — every status change logged here,
                      never updated, only inserted (regulated / disputable data)
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Enum, ForeignKey, Numeric, String, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.enums import ClaimStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Ownership ───────────────────────────────────────────────────────────
    claimant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Claim details ────────────────────────────────────────────────────────
    claim_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    claimed_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    incident_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── State machine ────────────────────────────────────────────────────────
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claimstatus"),
        nullable=False,
        default=ClaimStatus.draft,
        index=True,
    )

    # ── Soft-delete & timestamps ─────────────────────────────────────────────
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    # ── Relationships ────────────────────────────────────────────────────────
    claimant: Mapped["app.modules.users.models.User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[claimant_id], lazy="select"
    )
    assignee: Mapped["app.modules.users.models.User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[assigned_to], lazy="select"
    )
    status_history: Mapped[list["ClaimStatusHistory"]] = relationship(
        "ClaimStatusHistory",
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ClaimStatusHistory.changed_at",
    )

    __table_args__ = (
        # Composite index for the most common adjuster/admin query
        Index("ix_claims_status_claimant", "status", "claimant_id"),
    )

    def __repr__(self) -> str:
        return f"<Claim id={self.id} status={self.status} type={self.claim_type}>"


class ClaimStatusHistory(Base):
    """
    Append-only audit trail for claim status transitions.
    NEVER update rows in this table — only insert.
    This is the source of truth for the claim timeline UI.
    """
    __tablename__ = "claim_status_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[ClaimStatus | None] = mapped_column(
        Enum(ClaimStatus, name="claimstatus"),
        nullable=True,   # NULL = initial creation entry
    )
    to_status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claimstatus"),
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    # ── Relationships ────────────────────────────────────────────────────────
    claim: Mapped["Claim"] = relationship("Claim", back_populates="status_history")
    changed_by_user: Mapped["app.modules.users.models.User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[changed_by], lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<ClaimStatusHistory claim={self.claim_id} "
            f"{self.from_status}→{self.to_status}>"
        )
