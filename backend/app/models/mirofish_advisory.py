"""Persistence model for normalized MiroFish advisory outputs."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Numeric, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MiroFishAdvisory(Base):
    """Stores normalized advisory snapshots derived from MiroFish reports."""

    __tablename__ = "mirofish_advisories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    simulation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scenario_bias: Mapped[str] = mapped_column(String(20), nullable=False)
    tail_risk_score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    narrative_confidence: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_payload: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
