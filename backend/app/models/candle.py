"""Candle model for OHLCV market data."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Candle(Base):
    """Candle model for OHLCV market data."""

    __tablename__ = "candles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Candle details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # 1m, 5m, 15m, 1h, 1d

    # OHLCV data
    open: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint for symbol + timeframe + timestamp
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uix_candle_symbol_tf_ts"),
    )

    def __repr__(self) -> str:
        return (
            f"<Candle(symbol={self.symbol}, tf={self.timeframe}, ts={self.timestamp}, "
            f"close={self.close})>"
        )
