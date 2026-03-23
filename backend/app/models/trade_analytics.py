"""Trade analytics for post-trade metrics."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Integer, ForeignKey
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TradeAnalytics(Base):
    """Per-trade analytics to support PnL and risk reporting."""

    __tablename__ = "trade_analytics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    position_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    entry_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_pnl: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    net_pnl: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    fees: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    slippage: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    holding_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mae: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    mfe: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<TradeAnalytics(id={self.id}, symbol={self.symbol})>"
