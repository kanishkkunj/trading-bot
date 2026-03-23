"""Portfolio schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PositionResponse(BaseModel):
    """Position response schema."""

    id: str
    symbol: str
    quantity: int
    average_entry_price: float
    current_price: Optional[float]
    last_price_update: Optional[datetime]
    realized_pnl: float
    unrealized_pnl: float
    market_value: float
    cost_basis: float
    is_open: bool
    opened_at: datetime
    closed_at: Optional[datetime]
    updated_at: datetime

    class Config:
        from_attributes = True


class PortfolioSummary(BaseModel):
    """Portfolio summary schema."""

    total_positions: int
    open_positions: int
    total_market_value: float
    total_cost_basis: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl: float


class PortfolioHistory(BaseModel):
    """Portfolio history entry."""

    date: datetime
    total_value: float
    realized_pnl: float
    unrealized_pnl: float


class PnLResponse(BaseModel):
    """PnL response schema."""

    initial_capital: float
    cash: float
    equity: float
    long_exposure: float
    short_proceeds: float
    daily_pnl: float
    daily_realized_pnl: float
    daily_unrealized_pnl: float
    daily_pnl_pct: float
    total_pnl: float
    total_realized_pnl: float
    total_unrealized_pnl: float
    total_pnl_pct: float
    max_drawdown: float
    sharpe_ratio: Optional[float]


class TradeHistory(BaseModel):
    """Trade history entry."""

    id: str
    symbol: str
    side: str
    quantity: int
    price: float
    pnl: Optional[float]
    timestamp: datetime
