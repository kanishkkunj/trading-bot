"""Lightweight Cognee memory API client."""

from __future__ import annotations

from typing import Any, Iterable, Optional
from uuid import uuid4

import httpx

from app.config import get_settings


class CogneeClient:
    """Async client for Cognee memory service."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.COGNEE_API_KEY
        self.base_url = (base_url or settings.COGNEE_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

    @property
    def enabled(self) -> bool:
        """Return True when the API key is present."""
        return bool(self.api_key)

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._client.aclose()

    async def upsert_memory(
        self,
        *,
        scope: str,
        tags: Optional[Iterable[str]] = None,
        payload: dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Create or update a memory record.

        Returns the created record (or None if disabled/errors).
        """

        if not self.enabled:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key or str(uuid4()),
        }
        body = {
            "scope": scope,
            "tags": list(tags or []),
            "payload": payload,
        }

        try:
            resp = await self._client.post(f"{self.base_url}/v1/memories", json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            # Fail soft: trading flow should not break because of memory logging.
            print(f"Cognee memory upsert failed: {exc}")
            return None

    async def search_memories(
        self,
        *,
        scope: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        limit: int = 20,
    ) -> Optional[list[dict[str, Any]]]:
        """Query memories by scope/tags."""

        if not self.enabled:
            return None

        params: dict[str, Any] = {"limit": limit}
        if scope:
            params["scope"] = scope
        if tags:
            params["tags"] = ",".join(tags)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            resp = await self._client.get(f"{self.base_url}/v1/memories", params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"Cognee memory search failed: {exc}")
            return None
