import asyncio
import pytest

from app.data_ingestion.market_data_manager import MarketDataManager, MarketDataSource, Bar


class FakeSource(MarketDataSource):
    name = "fake"

    def __init__(self, bars=None, quote=None):
        self._bars = bars or []
        self._quote = quote or {"last_price": 100}

    async def get_history(self, symbol: str, interval: str, lookback: str):
        return self._bars

    async def get_quote(self, symbol: str):
        return self._quote


@pytest.mark.asyncio
async def test_history_from_first_source():
    mgr = MarketDataManager(redis_client=None)
    bars = [Bar(symbol="ABC", ts=1, open=1, high=2, low=1, close=1.5, volume=100, source="fake")]
    mgr.register_source(FakeSource(bars=bars))
    out = await mgr.get_history("ABC")
    assert out == bars


@pytest.mark.asyncio
async def test_quote_fallback_on_missing_price():
    mgr = MarketDataManager(redis_client=None)
    mgr.register_source(FakeSource(quote={}))
    mgr.register_source(FakeSource(quote={"last_price": 200}))
    out = await mgr.get_quote("ABC")
    assert out["last_price"] == 200
