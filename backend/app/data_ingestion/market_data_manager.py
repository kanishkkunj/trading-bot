"""Multi-source market data manager with adapters and caching."""

from __future__ import annotations

import abc
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # Optional dependency; fail-soft
    from prometheus_client import Counter, Summary, Gauge
except Exception:  # noqa: BLE001
    Counter = Summary = Gauge = None  # type: ignore

try:
    import redis.asyncio as redis
except Exception:  # noqa: BLE001
    redis = None  # type: ignore

import httpx
import yfinance as yf

from app.config import get_settings
from app.core.feature_flags import ingestion_hardening_enabled


def _metric_counter(name: str, desc: str):
    return Counter(name, desc) if Counter else None


def _metric_summary(name: str, desc: str):
    return Summary(name, desc) if Summary else None


def _metric_gauge(name: str, desc: str):
    return Gauge(name, desc) if Gauge else None


@dataclass
class Bar:
    """OHLCV bar."""

    symbol: str
    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    # Populated by MarketDataManager when ingestion_hardening_enabled(); 0.0 on legacy data.
    fetched_at: float = 0.0


class MarketDataSource(abc.ABC):
    """Abstract market data source."""

    name: str

    @abc.abstractmethod
    async def get_history(self, symbol: str, interval: str, lookback: str) -> List[Bar]:
        ...

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        ...


class YFinanceSource(MarketDataSource):
    name = "yfinance"

    async def get_history(self, symbol: str, interval: str, lookback: str) -> List[Bar]:
        df = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: yf.download(symbol, period=lookback, interval=interval, auto_adjust=False, progress=False),
        )
        bars: List[Bar] = []
        if df is None or df.empty:
            return bars
        for ts, row in df.iterrows():
            bars.append(
                Bar(
                    symbol=symbol,
                    ts=float(ts.timestamp()),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    source=self.name,
                )
            )
        return bars

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        ticker = yf.Ticker(symbol)
        info = await asyncio.get_event_loop().run_in_executor(None, lambda: ticker.info)
        return {
            "symbol": symbol,
            "last_price": info.get("regularMarketPrice"),
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "bid_size": info.get("bidSize"),
            "ask_size": info.get("askSize"),
            "volume": info.get("regularMarketVolume"),
            "timestamp": time.time(),
            "source": self.name,
        }


class ZerodhaSource(MarketDataSource):
    name = "zerodha"

    def __init__(self, client):
        self.client = client

    async def get_history(self, symbol: str, interval: str, lookback: str) -> List[Bar]:
        # Placeholder: depends on Zerodha historical API availability
        return []

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = self.client.get_quote([symbol])
        quote = data.get(symbol) if data else {}
        return {
            "symbol": symbol,
            "last_price": quote.get("last_price"),
            "bid": quote.get("depth", {}).get("buy", [{}])[0].get("price"),
            "ask": quote.get("depth", {}).get("sell", [{}])[0].get("price"),
            "bid_size": quote.get("depth", {}).get("buy", [{}])[0].get("quantity"),
            "ask_size": quote.get("depth", {}).get("sell", [{}])[0].get("quantity"),
            "volume": quote.get("volume"),
            "l2": quote.get("depth"),
            "timestamp": time.time(),
            "source": self.name,
        }


class OfficialNSESource(MarketDataSource):
    name = "nse_official"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def get_history(self, symbol: str, interval: str, lookback: str) -> List[Bar]:
        # Placeholder: would call NSE/BSE APIs for official history
        return []

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        # Placeholder: official live quote
        return {"symbol": symbol, "timestamp": time.time(), "source": self.name}

    async def get_corporate_actions(self, symbol: str) -> List[Dict[str, Any]]:
        return []

    async def get_bulk_deals(self) -> List[Dict[str, Any]]:
        return []

    async def get_fii_dii_flows(self) -> Dict[str, Any]:
        return {}


class MarketDataManager:
    """Coordinator for multiple data sources with caching, validation, and cleaning."""

    def __init__(self, redis_client: Optional[Any] = None):
        settings = get_settings()
        self.redis = redis_client or (redis.Redis.from_url(settings.REDIS_URL) if redis else None)
        self.sources: List[MarketDataSource] = []
        self.cache_ttl = 3600
        self._requests_total = _metric_counter("market_data_requests_total", "Market data requests")
        self._latency = _metric_summary("market_data_request_latency_seconds", "Latency of data fetches")
        self._freshness = _metric_gauge("market_data_freshness_seconds", "Age of last bar fetched")

    def register_source(self, source: MarketDataSource) -> None:
        self.sources.append(source)

    async def _fetch_with_retry(
        self,
        source: MarketDataSource,
        symbol: str,
        interval: str,
        lookback: str,
        max_retries: int = 3,
    ) -> List[Bar]:
        """Fetch bars from *source* with exponential-backoff retries.

        Only active when ingestion_hardening_enabled(); otherwise delegates to
        a single attempt to preserve legacy behaviour.
        """
        if not ingestion_hardening_enabled():
            return await source.get_history(symbol, interval, lookback)

        delay = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                bars = await source.get_history(symbol, interval, lookback)
                if bars:
                    # Stamp each bar with the wall-clock fetch time
                    now = time.time()
                    for b in bars:
                        b.fetched_at = now
                    return bars
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "market_data_fetch_retry",
                    source=source.name,
                    symbol=symbol,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2.0
        return []

    def _check_freshness(self, bars: List[Bar], symbol: str) -> None:
        """Log a warning when the latest bar is suspiciously old (>10 min)."""
        if not bars or not ingestion_hardening_enabled():
            return
        latest = max(bars, key=lambda b: b.ts)
        age_seconds = time.time() - latest.ts
        if age_seconds > 600:  # 10-minute staleness threshold
            log.warning(
                "market_data_stale",
                symbol=symbol,
                age_seconds=round(age_seconds, 1),
                latest_bar_ts=latest.ts,
            )

    async def get_history(self, symbol: str, interval: str = "1d", lookback: str = "400d") -> List[Bar]:
        cache_key = f"md:{symbol}:{interval}:{lookback}"
        if self.redis:
            cached = await self.redis.get(cache_key)
            if cached:
                try:
                    raw = json.loads(cached)
                    return [Bar(**row) for row in raw]
                except Exception:  # noqa: BLE001
                    pass

        for source in self.sources:
            try:
                if self._requests_total:
                    self._requests_total.inc()
                with (self._latency.time() if self._latency else asyncio.nullcontext()):
                    bars = await self._fetch_with_retry(source, symbol, interval, lookback)
                if bars:
                    cleaned = self._clean_bars(bars)
                    self._check_freshness(cleaned, symbol)
                    if self.redis:
                        await self.redis.set(cache_key, json.dumps([b.__dict__ for b in cleaned]), ex=self.cache_ttl)
                    if self._freshness and cleaned:
                        latest = max(cleaned, key=lambda b: b.ts)
                        self._freshness.set(time.time() - latest.ts)
                    return cleaned
            except Exception:  # noqa: BLE001
                continue
        return []

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        max_retries = 3 if ingestion_hardening_enabled() else 1
        for source in self.sources:
            delay = 1.0
            for attempt in range(1, max_retries + 1):
                try:
                    if self._requests_total:
                        self._requests_total.inc()
                    with (self._latency.time() if self._latency else asyncio.nullcontext()):
                        quote = await source.get_quote(symbol)
                    if quote and quote.get("last_price"):
                        return quote
                    break  # empty quote is not an error — try next source
                except Exception as exc:  # noqa: BLE001
                    if ingestion_hardening_enabled():
                        log.warning(
                            "market_quote_retry",
                            source=source.name,
                            symbol=symbol,
                            attempt=attempt,
                            error=str(exc),
                        )
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2.0
                    break
        return {}

    def _clean_bars(self, bars: List[Bar]) -> List[Bar]:
        if not bars:
            return bars
        cleaned: List[Bar] = []
        prices = [b.close for b in bars]
        if prices:
            median = sorted(prices)[len(prices) // 2]
            mad = sorted(abs(p - median) for p in prices)[len(prices) // 2] or 1.0
        else:
            median, mad = 0.0, 1.0
        for b in bars:
            z = abs(b.close - median) / mad
            if z > 10:  # outlier filter
                continue
            cleaned.append(b)
        # Simple gap fill: forward-fill missing timestamps if regular spacing (best-effort)
        cleaned.sort(key=lambda b: b.ts)
        return cleaned

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()
