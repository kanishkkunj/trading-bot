"""Order schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.order import OrderSide, OrderType, OrderStatus


class OrderBase(BaseModel):
    """Base order schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int = Field(..., gt=0)
    price: Optional[float] = Field(None, gt=0)
    trigger_price: Optional[float] = Field(None, gt=0)


class OrderCreate(OrderBase):
    """Order creation schema."""

    strategy_id: Optional[str] = None
    signal_id: Optional[str] = None


class OrderUpdate(BaseModel):
    """Order update schema."""

    quantity: Optional[int] = Field(None, gt=0)
    price: Optional[float] = Field(None, gt=0)


class OrderResponse(OrderBase):
    """Order response schema."""

    id: str
    user_id: str
    filled_quantity: int
    average_price: Optional[float]
    status: OrderStatus
    status_message: Optional[str]
    broker_order_id: Optional[str]
    broker: str
    strategy_id: Optional[str]
    signal_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    placed_at: Optional[datetime]
    filled_at: Optional[datetime]

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Order list response schema."""

    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class OrderFilter(BaseModel):
    """Order filter schema."""

    symbol: Optional[str] = None
    side: Optional[OrderSide] = None
    status: Optional[OrderStatus] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
