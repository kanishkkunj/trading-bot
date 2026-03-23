"""Order model for tracking trades."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import String, Numeric, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class OrderSide(str, PyEnum):
    """Order side (BUY or SELL)."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, PyEnum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderStatus(str, PyEnum):
    """Order status."""

    PENDING = "PENDING"
    PLACED = "PLACED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TimeInForce(str, PyEnum):
    """Time in force policies."""

    DAY = "DAY"
    IOC = "IOC"
    FOK = "FOK"
    GTC = "GTC"
    GTD = "GTD"


class ProductType(str, PyEnum):
    """Product type for risk/margin handling."""

    CASH = "CASH"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class Order(Base):
    """Order model for tracking trades."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # user_id removed for single-user mode

    # Order details
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[OrderSide] = mapped_column(Enum(OrderSide), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    filled_quantity: Mapped[int] = mapped_column(default=0, nullable=False)

    # Pricing
    price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    trigger_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)
    average_price: Mapped[float | None] = mapped_column(Numeric(15, 4), nullable=True)

    # Status
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False, index=True
    )
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Broker details
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    broker: Mapped[str] = mapped_column(String(50), default="PAPER", nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Duration/product controls
    time_in_force: Mapped[TimeInForce] = mapped_column(
        Enum(TimeInForce), nullable=False, default=TimeInForce.DAY
    )
    product_type: Mapped[ProductType] = mapped_column(
        Enum(ProductType), nullable=False, default=ProductType.CASH
    )
    parent_order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Strategy tracking
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    signal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    regime_label: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Costs and risk
    expected_slippage: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    fees: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(postgresql.JSONB, nullable=True)

    # Relationships removed for single-user mode

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, symbol={self.symbol}, side={self.side}, status={self.status})>"
