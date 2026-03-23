"""Thin wrapper around Kite Connect for live quotes."""

from __future__ import annotations

import os
from typing import Optional

from kiteconnect import KiteConnect


class ZerodhaClient:
    """Lightweight Zerodha client for quotes/LTP.

    Expects env vars:
      - ZERODHA_API_KEY
      - ZERODHA_ACCESS_TOKEN
    Optionally you can also supply ZERODHA_API_SECRET if you need to re-generate tokens
    in a different flow (not used here).
    """

    def __init__(self):
        self.api_key = os.getenv("ZERODHA_API_KEY")
        self.access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
        self.enabled = bool(self.api_key and self.access_token)
        self.kite: Optional[KiteConnect] = None

        if self.enabled:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)

    def get_quote(self, symbols: list[str]) -> dict:
        """Return quote payload for given symbols."""
        if not self.enabled or not self.kite:
            raise RuntimeError("Zerodha client not configured")
        return self.kite.quote(symbols)

    def get_ltp(self, symbols: list[str]) -> dict:
        """Return last traded price for given symbols."""
        if not self.enabled or not self.kite:
            raise RuntimeError("Zerodha client not configured")
        return self.kite.ltp(symbols)

    def get_single_ltp(self, symbol: str) -> Optional[float]:
        """Convenience helper for single symbol."""
        if not self.enabled or not self.kite:
            return None
        try:
            data = self.kite.ltp([symbol])
            if symbol in data and "last_price" in data[symbol]:
                return float(data[symbol]["last_price"])
        except Exception:
            return None
        return None
