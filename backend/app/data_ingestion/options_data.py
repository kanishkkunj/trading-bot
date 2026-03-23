"""Options data integrator: chain fetch and surface metrics."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

try:
    from prometheus_client import Summary
except Exception:  # noqa: BLE001
    Summary = None  # type: ignore

import structlog

from app.core.feature_flags import ingestion_hardening_enabled

log = structlog.get_logger()

# Maximum acceptable age for an options chain before it is considered stale.
_DEFAULT_MAX_AGE_SECONDS = 300  # 5 minutes


class OptionsData:
    def __init__(self, max_age_seconds: int = _DEFAULT_MAX_AGE_SECONDS):
        self._latency = Summary("options_chain_latency_seconds", "Latency of options chain fetch") if Summary else None
        self.max_age_seconds = max_age_seconds

    async def fetch_chain(self, symbol: str) -> Dict[str, Any]:
        """Fetch the options chain for *symbol*.

        When ingestion_hardening_enabled(), retries up to 3 times with
        exponential back-off and includes fetch metadata in the returned dict.
        Returns a dict with keys: expirations, chains, fetch_meta.
        """
        if ingestion_hardening_enabled():
            return await self._fetch_with_retry(symbol)
        return self._wrap_result(await self._fetch_once(symbol), retry_count=0)

    async def _fetch_once(self, symbol: str) -> Dict[str, Any]:
        ticker = yf.Ticker(symbol)
        if self._latency:
            with self._latency.time():
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self._fetch_sync(ticker))
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self._fetch_sync(ticker))

    async def _fetch_with_retry(self, symbol: str, max_retries: int = 3) -> Dict[str, Any]:
        """Retry the chain fetch with exponential back-off.

        NSE option chains can return empty or incomplete results on transient
        network issues; retrying and refreshing the ticker object (analogous to
        a session/cookie refresh) clears stale connection state.
        """
        delay = 1.0
        last_result: Dict[str, Any] = {}
        for attempt in range(1, max_retries + 1):
            try:
                result = await self._fetch_once(symbol)
                if result.get("expirations"):
                    return self._wrap_result(result, retry_count=attempt - 1)
                # Empty result: treat as soft failure and retry
                log.warning(
                    "options_chain_empty",
                    symbol=symbol,
                    attempt=attempt,
                )
                last_result = result
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "options_chain_fetch_error",
                    symbol=symbol,
                    attempt=attempt,
                    error=str(exc),
                )
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= 2.0
        log.error("options_chain_fetch_failed", symbol=symbol, max_retries=max_retries)
        return self._wrap_result(last_result or {"expirations": [], "chains": {}}, retry_count=max_retries)

    def _wrap_result(self, raw: Dict[str, Any], retry_count: int) -> Dict[str, Any]:
        """Attach fetch metadata so callers can perform staleness checks."""
        fetched_at = time.time()
        return {
            **raw,
            "fetch_meta": {
                "fetched_at": fetched_at,
                "retry_count": retry_count,
                "is_stale": False,  # freshness evaluated by consumers after ttl elapses
            },
        }

    def is_stale(self, chain: Dict[str, Any]) -> bool:
        """Return True if the chain was fetched more than *max_age_seconds* ago."""
        meta = chain.get("fetch_meta", {})
        fetched_at = meta.get("fetched_at", 0.0)
        if fetched_at == 0.0:
            return False  # legacy data without metadata: don't block
        return (time.time() - fetched_at) > self.max_age_seconds

    def _fetch_sync(self, ticker) -> Dict[str, Any]:
        expirations = ticker.options or []
        chains = {}
        for expiry in expirations:
            try:
                opt = ticker.option_chain(expiry)
                chains[expiry] = {
                    "calls": opt.calls.to_dict("records"),
                    "puts": opt.puts.to_dict("records"),
                }
            except Exception:  # noqa: BLE001
                continue
        return {"expirations": expirations, "chains": chains}

    def compute_iv_surface(self, chain: Dict[str, Any]) -> Dict[str, Any]:
        surface: List[Tuple[str, float, float, float]] = []  # expiry, strike, call_iv, put_iv
        for expiry, data in chain.get("chains", {}).items():
            for row in data.get("calls", []):
                surface.append((expiry, row.get("strike"), row.get("impliedVolatility"), None))
            for row in data.get("puts", []):
                surface.append((expiry, row.get("strike"), None, row.get("impliedVolatility")))
        return {"surface": surface}

    def compute_skew_term_structure(self, chain: Dict[str, Any]) -> Dict[str, float]:
        skew: Dict[str, float] = {}
        for expiry, data in chain.get("chains", {}).items():
            calls = [r for r in data.get("calls", []) if r.get("impliedVolatility")]
            puts = [r for r in data.get("puts", []) if r.get("impliedVolatility")]
            if not calls or not puts:
                continue
            avg_call_iv = sum(r["impliedVolatility"] for r in calls) / len(calls)
            avg_put_iv = sum(r["impliedVolatility"] for r in puts) / len(puts)
            skew[expiry] = avg_call_iv - avg_put_iv
        return skew

