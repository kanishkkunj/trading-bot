"""Bot manager service — controls the paper trading loop lifecycle.

A module-level singleton (bot_manager) that wraps PaperTradeService in an
asyncio background task.  Start/stop can be triggered from the /api/v1/bot
endpoints without restarting the FastAPI process.

Design notes
------------
- The background task opens a *new* database session each cycle using
  AsyncSessionLocal so it is never sharing a session with request handlers.
- Alerts are kept in a capped in-memory ring buffer (MAX_ALERTS entries).
- Statistics are accumulated across the process lifetime; they reset on server
  restart.  For persistent stats, wire bot_manager into the existing signals /
  trades tables.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

log = structlog.get_logger()

_MAX_ALERTS = 200


class BotManager:
    """Manages start/stop of the autonomous paper trading loop."""

    def __init__(self) -> None:
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._started_at: Optional[datetime] = None
        self._stopped_at: Optional[datetime] = None
        self._config: Dict[str, Any] = {}
        self._alerts: List[Dict[str, Any]] = []
        self._stats: Dict[str, Any] = {
            "total_cycles": 0,
            "total_orders": 0,
            "errors": 0,
            # Phase 0 baseline counters — incremented by risk gates and freshness checks
            "stale_data_blocks": 0,
            "close_window_blocks": 0,
            "model_validation_blocks": 0,
        }

    # ------------------------------------------------------------------ internal

    def _push_alert(self, level: str, message: str) -> None:
        self._alerts.append({
            "level": level,
            "message": message,
            "time": datetime.utcnow().isoformat(),
        })
        if len(self._alerts) > _MAX_ALERTS:
            self._alerts.pop(0)

    async def _run_loop(self, interval_seconds: int) -> None:
        """Main trading loop — runs PaperTradeService once per interval."""
        from app.db.session import AsyncSessionLocal
        from app.services.paper_trade_service import PaperTradeService

        log.info("bot_loop_started", interval_seconds=interval_seconds)
        self._push_alert("INFO", "Bot loop started")

        while True:
            try:
                async with AsyncSessionLocal() as db:
                    service = PaperTradeService(db)
                    executed = await service.run(
                        user_id=1,
                        top_k=self._config.get("top_k", 5),
                    )
                self._stats["total_cycles"] += 1
                self._stats["total_orders"] += len(executed)
                if executed:
                    self._push_alert("TRADE", f"Cycle complete — {len(executed)} orders executed")
                    log.info("bot_cycle_complete", orders=len(executed))
                else:
                    log.info("bot_cycle_no_orders")
            except asyncio.CancelledError:
                log.info("bot_loop_cancelled")
                break
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                self._push_alert("ERROR", str(exc))
                log.error("bot_loop_error", error=str(exc))

            await asyncio.sleep(interval_seconds)

        self._push_alert("INFO", "Bot loop ended")

    # ------------------------------------------------------------------ public API

    def start_bot(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Start the trading loop.  Idempotent — returns current state if already running."""
        if self.is_running:
            return {
                "status": "already_running",
                "started_at": self._started_at.isoformat() if self._started_at else None,
            }

        self._config = config or {}
        self._started_at = datetime.utcnow()
        self._stopped_at = None
        interval = int(self._config.get("interval_seconds", 60))

        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._run_loop(interval_seconds=interval))
        except RuntimeError as exc:
            return {"status": "error", "detail": str(exc)}

        self.is_running = True
        self._push_alert("INFO", "Bot started")
        log.info("bot_started", config=self._config)
        return {"status": "started", "started_at": self._started_at.isoformat()}

    def stop_bot(self) -> Dict[str, Any]:
        """Stop the trading loop gracefully."""
        if not self.is_running:
            return {"status": "not_running"}

        if self._task and not self._task.done():
            self._task.cancel()

        self.is_running = False
        self._stopped_at = datetime.utcnow()
        self._push_alert("INFO", "Bot stopped")
        log.info("bot_stopped")
        return {"status": "stopped", "stopped_at": self._stopped_at.isoformat()}

    def get_status(self) -> Dict[str, Any]:
        """Return current bot state."""
        return {
            "is_running": self.is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "stopped_at": self._stopped_at.isoformat() if self._stopped_at else None,
            "config": self._config,
        }

    # ------------------------------------------------------------------ counters

    def record_stale_data_block(self) -> None:
        """Increment stale-data block counter (called by freshness gate)."""
        self._stats["stale_data_blocks"] += 1
        log.debug("bot_stat_stale_data_block", total=self._stats["stale_data_blocks"])

    def record_close_window_block(self) -> None:
        """Increment close-window block counter (called by market-close guard)."""
        self._stats["close_window_blocks"] += 1
        log.debug("bot_stat_close_window_block", total=self._stats["close_window_blocks"])

    def record_model_validation_block(self) -> None:
        """Increment model-validation block counter (called by walk-forward gate)."""
        self._stats["model_validation_blocks"] += 1
        log.debug("bot_stat_model_validation_block", total=self._stats["model_validation_blocks"])

    def get_statistics(self) -> Dict[str, Any]:
        """Return accumulated performance counters."""
        return dict(self._stats)

    def get_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent *limit* alerts."""
        limit = max(1, min(limit, _MAX_ALERTS))
        return self._alerts[-limit:]

    def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge new config keys into the current bot config."""
        self._config.update(config)
        self._push_alert("INFO", f"Config updated: {list(config.keys())}")
        return dict(self._config)


# Module-level singleton — imported by api/bot.py and optionally by the trading loop
bot_manager = BotManager()
