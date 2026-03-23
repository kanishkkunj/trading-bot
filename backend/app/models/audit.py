"""Audit log model for tracking all actions."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AuditLog(Base):
    """Audit log model for tracking all actions."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Action details
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # order, position, signal, etc.
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # User information
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Details
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, entity={self.entity_type})>"
