"""Institutional flows (FII/DII), promoter, bulk/block deals."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import httpx


class InstitutionalFlow:
    def __init__(self, base_url: str = "https://nse-india.example/api"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=5.0)

    async def fii_dii(self) -> Dict[str, Any]:
        return await self._get("/fii-dii")

    async def bulk_deals(self) -> List[Dict[str, Any]]:
        return await self._get("/bulk-deals")

    async def block_deals(self) -> List[Dict[str, Any]]:
        return await self._get("/block-deals")

    async def promoter_activity(self) -> List[Dict[str, Any]]:
        return await self._get("/promoter-transactions")

    async def _get(self, path: str):
        try:
            resp = await self.client.get(f"{self.base_url}{path}")
            resp.raise_for_status()
            return resp.json()
        except Exception:  # noqa: BLE001
            return []

    async def close(self):
        await self.client.aclose()
