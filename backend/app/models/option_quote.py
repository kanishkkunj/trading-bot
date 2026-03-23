"""Option quote snapshots."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, Integer, Enum
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class OptionType(str, PyEnum):
    """Option contract type."""

    CALL = "CALL"
    PUT = "PUT"


class OptionQuote(Base):
    """Per-contract option quote with Greeks."""

    __tablename__ = "option_quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    option_symbol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    expiry: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    strike: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    option_type: Mapped[OptionType] = mapped_column(Enum(OptionType), nullable=False)
    bid: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    ask: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    bid_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ask_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    implied_vol: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    delta: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    gamma: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    vega: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    theta: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    rho: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    underlying_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<OptionQuote(id={self.id}, option={self.option_symbol}, ts={self.as_of})>"
