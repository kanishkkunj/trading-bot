"""System health monitoring: latencies, DB pool, external APIs."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import structlog

try:  # Optional Prometheus dependency
    from prometheus_client import Gauge, Histogram
except Exception:  # pragma: no cover
    class _NoOp:  # type: ignore
        def labels(self, *_, **__):
            return self

        def set(self, *_args, **_kwargs):
            return None

        def observe(self, *_args, **_kwargs):
            return None

    def Gauge(*_args, **_kwargs):
        return _NoOp()

    def Histogram(*_args, **_kwargs):
        return _NoOp()

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore

log = structlog.get_logger()


class SystemHealthMonitor:
    """Collects latency and availability signals across subsystems."""

    def __init__(self) -> None:
        self.data_latency = Histogram("data_pipeline_latency_ms", "Data pipeline latency (ms)")
        self.model_latency = Histogram("model_inference_ms", "Model inference latency (ms)")
        self.db_pool_gauge = Gauge("db_pool_usage", "DB pool in-use vs max", ["metric"])
        self.api_health_gauge = Gauge("external_api_health", "External API health (1=up)", ["service"])
        self.api_latency = Histogram("external_api_latency_ms", "External API latency (ms)", ["service"])
        self._last_api_status: Dict[str, bool] = {}

    def observe_data_latency(self, latency_ms: float) -> None:
        self.data_latency.observe(latency_ms)

    def observe_model_latency(self, latency_ms: float) -> None:
        self.model_latency.observe(latency_ms)

    def update_db_pool(self, in_use: int, max_size: int) -> None:
        max_size = max(max_size, 1)
        self.db_pool_gauge.labels(metric="in_use").set(in_use)
        self.db_pool_gauge.labels(metric="max").set(max_size)
        self.db_pool_gauge.labels(metric="utilization_pct").set((in_use / max_size) * 100)

    async def check_external_api(self, name: str, url: str, timeout: float = 3.0) -> Dict[str, Any]:
        if not httpx:
            log.warning("httpx_missing_for_api_health", service=name)
            return {"service": name, "ok": False, "latency_ms": None}
        start = time.perf_counter()
        ok = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                ok = resp.status_code < 400
        except Exception as exc:  # noqa: BLE001
            log.warning("api_health_failed", service=name, error=str(exc))
        latency_ms = (time.perf_counter() - start) * 1000
        self.api_health_gauge.labels(service=name).set(1 if ok else 0)
        self.api_latency.labels(service=name).observe(latency_ms)
        self._last_api_status[name] = ok
        return {"service": name, "ok": ok, "latency_ms": latency_ms}

    async def check_many_apis(self, targets: Dict[str, str], timeout: float = 3.0) -> Dict[str, Dict[str, Any]]:
        tasks = [self.check_external_api(name, url, timeout=timeout) for name, url in targets.items()]
        results = await asyncio.gather(*tasks)
        return {r["service"]: r for r in results}

    def snapshot(self) -> Dict[str, Any]:
        return {"apis": dict(self._last_api_status)}
