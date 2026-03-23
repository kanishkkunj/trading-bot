"""Market data fetcher."""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candle import Candle
from app.schemas.market import HistoricalDataRequest
from app.services.market_service import MarketService

logger = structlog.get_logger()


class DataFetcher:
    """Fetches and stores market data."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.market_service = MarketService(db)

    async def fetch_and_store(
        self,
        symbol: str,
        timeframe: str = "1d",
        days: int = 365,
    ) -> int:
        """Fetch historical data and store in database."""
        logger.info(
            "Fetching historical data",
            symbol=symbol,
            timeframe=timeframe,
            days=days,
        )

        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days)

        request = HistoricalDataRequest(
            symbol=symbol,
            timeframe=timeframe,
            from_date=from_date,
            to_date=to_date,
        )

        candles = await self.market_service.get_historical_data(request)

        logger.info(
            "Data fetch complete",
            symbol=symbol,
            candles_fetched=len(candles),
        )

        return len(candles)

    async def fetch_nifty50(self, timeframe: str = "1d", days: int = 365) -> dict:
        """Fetch data for all NIFTY 50 stocks."""
        results = {}

        for symbol in self.market_service.NIFTY50_SYMBOLS:
            try:
                count = await self.fetch_and_store(symbol, timeframe, days)
                results[symbol] = {"status": "success", "count": count}
            except Exception as e:
                logger.error("Failed to fetch data", symbol=symbol, error=str(e))
                results[symbol] = {"status": "error", "error": str(e)}

        return results

    async def update_latest(self, symbols: Optional[list[str]] = None) -> dict:
        """Update latest data for symbols."""
        if symbols is None:
            symbols = self.market_service.NIFTY50_SYMBOLS

        results = {}

        for symbol in symbols:
            try:
                count = await self.fetch_and_store(symbol, "1d", days=1)
                results[symbol] = {"status": "success", "count": count}
            except Exception as e:
                logger.error("Failed to update data", symbol=symbol, error=str(e))
                results[symbol] = {"status": "error", "error": str(e)}

        return results
