"""Level 2 order book snapshots."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Integer
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OrderBookSnapshot(Base):
    """Aggregated depth per timestamp/symbol."""

    __tablename__ = "order_book_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    venue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mid_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    best_bid: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    spread: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    bid_levels: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    ask_levels: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)
    buy_depth: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    sell_depth: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    imbalance: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<OrderBookSnapshot(symbol={self.symbol}, ts={self.as_of})>"
