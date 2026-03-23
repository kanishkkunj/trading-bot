"""Signal model for trading signals."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Enum as SQLEnum, Text, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SignalAction(str, PyEnum):
    """Signal action type."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalStatus(str, PyEnum):
    """Signal status."""

    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class Signal(Base):
    """Signal model for trading signals."""

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Signal details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[SignalAction] = mapped_column(SQLEnum(SignalAction), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    # Suggested order parameters
    suggested_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)

    # Model information
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    features_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_set: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Regime and horizon context
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    regime_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    horizon_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[SignalStatus] = mapped_column(
        SQLEnum(SignalStatus), default=SignalStatus.PENDING, nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Related order
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prediction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Risk/expected outcomes
    expected_return: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    expected_volatility: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Signal(id={self.id}, symbol={self.symbol}, action={self.action}, "
            f"confidence={self.confidence})>"
        )
