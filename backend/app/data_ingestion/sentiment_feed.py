"""News and sentiment feed integrator."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

try:
    from prometheus_client import Summary
except Exception:  # noqa: BLE001
    Summary = None  # type: ignore


class SentimentFeed:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://newsapi.org/v2"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=5.0)
        self._latency = Summary("news_feed_latency_seconds", "Latency of news fetch") if Summary else None

    async def headlines(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        params = {"q": query, "pageSize": limit, "apiKey": self.api_key}
        if self._latency:
            with self._latency.time():
                return await self._fetch("/everything", params)
        return await self._fetch("/everything", params)

    async def earnings_calendar(self) -> List[Dict[str, Any]]:
        # Placeholder: integrate with provider that offers earnings
        return []

    async def economic_events(self) -> List[Dict[str, Any]]:
        # Placeholder: integrate with macro calendar
        return []

    async def _fetch(self, path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            resp = await self.client.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("articles", [])
        except Exception:  # noqa: BLE001
            return []

    async def close(self):
        await self.client.aclose()
