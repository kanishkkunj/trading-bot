"""Risk metrics time series."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RiskMetric(Base):
    """Risk metrics aggregated per symbol/time window."""

    __tablename__ = "risk_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    window: Mapped[str | None] = mapped_column(String(20), nullable=True)
    volatility: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    var_95: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    cvar_95: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    beta: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    drawdown: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    exposure: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    leverage: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    stress_scenarios: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<RiskMetric(symbol={self.symbol}, as_of={self.as_of})>"
