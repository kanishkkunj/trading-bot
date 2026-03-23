"""Position model for tracking holdings."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, ForeignKey, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base




class Position(Base):
    """Position model for tracking holdings."""

    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))


    # Position details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_entry_price: Mapped[float] = mapped_column(Numeric(15, 4), default=0, nullable=False)

    # Current market data
    current_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    last_price_update: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # PnL tracking
    realized_pnl: Mapped[float] = mapped_column(Numeric(15, 4), default=0, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(15, 4), default=0, nullable=False)

    # Risk and exposure
    leverage: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    exposure: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    value_at_risk: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    # Position status
    is_open: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )



    @property
    def market_value(self) -> float:
        """Calculate current market value of position."""
        if self.current_price:
            return abs(float(self.quantity)) * float(self.current_price)
        return 0.0

    @property
    def cost_basis(self) -> float:
        """Calculate cost basis of position."""
        return abs(float(self.quantity)) * float(self.average_entry_price)

    def __repr__(self) -> str:
        return f"<Position(id={self.id}, symbol={self.symbol}, qty={self.quantity})>"
