"""Options data integrator: chain fetch and surface metrics."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import yfinance as yf

try:
    from prometheus_client import Summary
except Exception:  # noqa: BLE001
    Summary = None  # type: ignore


class OptionsData:
    def __init__(self):
        self._latency = Summary("options_chain_latency_seconds", "Latency of options chain fetch") if Summary else None

    async def fetch_chain(self, symbol: str) -> Dict[str, Any]:
        ticker = yf.Ticker(symbol)
        if self._latency:
            with self._latency.time():
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self._fetch_sync(ticker))
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self._fetch_sync(ticker))

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
