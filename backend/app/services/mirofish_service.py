"""MiroFish sidecar client.

This module keeps MiroFish integration advisory-only and isolated from
execution-critical services.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import get_settings


class MiroFishService:
    """HTTP client wrapper for calling a MiroFish sidecar."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.MIROFISH_ENABLED)

    def _build_url(self, path: str) -> str:
        base = self.settings.MIROFISH_BASE_URL.rstrip("/")
        prefix = self.settings.MIROFISH_API_PREFIX.strip()
        if not path.startswith("/"):
            path = f"/{path}"
        if prefix:
            if not prefix.startswith("/"):
                prefix = f"/{prefix}"
            prefix = prefix.rstrip("/")
        return f"{base}{prefix}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.MIROFISH_API_KEY:
            headers["Authorization"] = f"Bearer {self.settings.MIROFISH_API_KEY}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_payload: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "ok": False,
                "status": "disabled",
                "message": "MiroFish integration is disabled",
                "degraded": False,
                "data": None,
                "error": None,
            }

        url = self._build_url(path)
        timeout = httpx.Timeout(self.settings.MIROFISH_TIMEOUT_SECONDS)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=self._headers(),
                    json=json_payload,
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                return {
                    "ok": True,
                    "status": "success",
                    "message": "MiroFish request completed",
                    "degraded": False,
                    "data": payload,
                    "error": None,
                }
        except Exception as exc:  # noqa: BLE001
            if self.settings.MIROFISH_FAIL_OPEN:
                return {
                    "ok": False,
                    "status": "degraded",
                    "message": "MiroFish unavailable; fail-open fallback active",
                    "degraded": True,
                    "data": None,
                    "error": str(exc),
                }
            return {
                "ok": False,
                "status": "error",
                "message": "MiroFish request failed",
                "degraded": False,
                "data": None,
                "error": str(exc),
            }

    async def health(self) -> dict[str, Any]:
        """Check MiroFish health endpoint."""
        if not self.enabled:
            return {
                "ok": False,
                "status": "disabled",
                "message": "MiroFish integration is disabled",
                "degraded": False,
                "data": None,
                "error": None,
            }
        return await self._request("GET", "/health")

    async def create_simulation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a simulation in MiroFish."""
        return await self._request("POST", "/simulation/create", json_payload=payload)

    async def prepare_simulation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Prepare simulation profiles/config in MiroFish."""
        return await self._request("POST", "/simulation/prepare", json_payload=payload)

    async def start_simulation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start simulation run in MiroFish."""
        return await self._request("POST", "/simulation/start", json_payload=payload)

    async def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start report generation for a simulation."""
        return await self._request("POST", "/report/generate", json_payload=payload)

    async def report_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Poll report generation status."""
        return await self._request("POST", "/report/generate/status", json_payload=payload)

    async def report_by_simulation(self, simulation_id: str) -> dict[str, Any]:
        """Fetch report details for a simulation id."""
        return await self._request("GET", f"/report/by-simulation/{simulation_id}")
