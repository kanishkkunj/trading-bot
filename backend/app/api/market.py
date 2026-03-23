"""Market data API routes."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.schemas.market import (
    CandleResponse,
    HistoricalDataRequest,
    HistoricalDataResponse,
    QuoteResponse,
    WatchlistItem,
)
from app.services.market_service import MarketService
from app.services.data_validation_service import OHLCVValidator

router = APIRouter()


@router.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> QuoteResponse:
    """Get live quote for a symbol."""
    market_service = MarketService(db)
    quote = await market_service.get_live_quote(symbol)

    if not quote:
        raise HTTPException(
            status_code=404,
            detail=f"Quote not found for symbol: {symbol}",
        )

    return QuoteResponse(**quote)


@router.get("/historical/{symbol}", response_model=HistoricalDataResponse)
async def get_historical_data(
    symbol: str,
    timeframe: str = Query(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$"),
    days: int = Query(default=30, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
) -> HistoricalDataResponse:
    """Get historical OHLCV data."""
    market_service = MarketService(db)

    to_date = datetime.utcnow()
    from_date = to_date - timedelta(days=days)

    request = HistoricalDataRequest(
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
    )

    candles = await market_service.get_historical_data(request)

    return HistoricalDataResponse(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
    )


@router.get("/nifty50", response_model=list[WatchlistItem])
async def get_nifty50_list(
    db: AsyncSession = Depends(get_db),
) -> list[WatchlistItem]:
    """Get NIFTY 50 stock list with quotes."""
    market_service = MarketService(db)
    stocks = await market_service.get_nifty50_list()

    return [WatchlistItem(**stock) for stock in stocks]


@router.post("/ingest/{symbol}")
async def ingest_historical_data(
    symbol: str,
    timeframe: str = Query(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$"),
    days: int = Query(default=365, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest historical data for a symbol."""
    market_service = MarketService(db)

    try:
        count = await market_service.ingest_historical_data(symbol, timeframe, days)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles_ingested": count,
            "status": "success",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest data: {str(e)}",
        )


@router.get("/validate/{symbol}", summary="Validate OHLCV data quality for a symbol")
async def validate_market_data(
    symbol: str,
    timeframe: str = Query(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$"),
    days: int = Query(default=30, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Run data quality checks on historical OHLCV candles for a symbol.

    Returns a report with pass/fail flags for OHLC relationships, volume,
    gap detection, and outlier detection.
    """
    market_service = MarketService(db)

    to_date = datetime.utcnow()
    from_date = to_date - timedelta(days=days)

    request = HistoricalDataRequest(
        symbol=symbol,
        timeframe=timeframe,
        from_date=from_date,
        to_date=to_date,
    )

    candles = await market_service.get_historical_data(request)
    if not candles:
        raise HTTPException(status_code=404, detail=f"No candles found for {symbol}")

    records = [
        {
            "time": c.time if hasattr(c, "time") else c.get("time"),
            "open": c.open if hasattr(c, "open") else c.get("open"),
            "high": c.high if hasattr(c, "high") else c.get("high"),
            "low": c.low if hasattr(c, "low") else c.get("low"),
            "close": c.close if hasattr(c, "close") else c.get("close"),
            "volume": c.volume if hasattr(c, "volume") else c.get("volume"),
        }
        for c in candles
    ]

    validator = OHLCVValidator()
    validator.load_from_records(records)
    report = validator.run_full_validation()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles_checked": report.total_rows,
        "is_valid": report.is_valid,
        "issues": report.issues,
        "warnings": report.warnings,
        "details": report.details,
    }
