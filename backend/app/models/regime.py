"""Regime detection model."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Text, Enum
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RegimeType(str, PyEnum):
    """Market regime classification."""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    VOLATILITY_CRISIS = "VOLATILITY_CRISIS"
    LIQUIDITY_CRUNCH = "LIQUIDITY_CRUNCH"


class Regime(Base):
    """Detected market regimes over time."""

    __tablename__ = "regimes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    regime_type: Mapped[RegimeType] = mapped_column(Enum(RegimeType), nullable=False)
    label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detector_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    symbols: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    features_snapshot: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Regime(id={self.id}, type={self.regime_type}, start={self.start_time})>"
