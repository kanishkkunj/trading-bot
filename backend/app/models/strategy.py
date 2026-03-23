"""Strategy configuration model."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, DateTime, Boolean, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StrategyConfig(Base):
    """Strategy configuration model."""

    __tablename__ = "strategy_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Strategy details
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)

    # Strategy parameters
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Model reference
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Universe
    symbols: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<StrategyConfig(id={self.id}, name={self.name}, active={self.is_active})>"
