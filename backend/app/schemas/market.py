"""Market data schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CandleResponse(BaseModel):
    """Candle/OHLCV response schema."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    class Config:
        from_attributes = True


class QuoteResponse(BaseModel):
    """Live quote response schema."""

    symbol: str
    last_price: float
    change: float
    change_percent: float
    bid: Optional[float]
    ask: Optional[float]
    bid_qty: Optional[int]
    ask_qty: Optional[int]
    volume: int
    timestamp: datetime


class HistoricalDataRequest(BaseModel):
    """Historical data request schema."""

    symbol: str = Field(..., min_length=1, max_length=20)
    timeframe: str = Field(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$")
    from_date: datetime
    to_date: datetime


class HistoricalDataResponse(BaseModel):
    """Historical data response schema."""

    symbol: str
    timeframe: str
    candles: list[CandleResponse]


class WatchlistItem(BaseModel):
    """Watchlist item schema."""

    symbol: str
    name: Optional[str]
    last_price: float
    change: float
    change_percent: float
