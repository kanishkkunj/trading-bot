"""Baseline metrics capture and comparison.

Records key performance indicators before and after each implementation phase
so we can measure concrete impact.  Writes snapshots to structlog and
optionally to a JSON file for offline diffing.

Tracked metrics:
    signal_count           — total signals generated per session
    signal_precision       — accepted_signals / total_signals
    net_pnl                — cumulative paper P&L
    max_drawdown           — maximum peak-to-trough drawdown seen
    stale_data_incidents   — market data rejected as stale
    order_rejection_rate   — rejected orders / total order attempts
    close_window_blocks    — entries blocked by market-close cutoff
    model_validation_fails — signals blocked by walk-forward gate
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional, cast

import structlog

log = structlog.get_logger()


@dataclass
class Snapshot:
    """Point-in-time snapshot of key KPIs."""

    captured_at: str
    phase_label: str
    signal_count: int = 0
    accepted_signals: int = 0
    rejected_signals: int = 0
    net_pnl: float = 0.0
    peak_pnl: float = 0.0
    max_drawdown: float = 0.0
    stale_data_incidents: int = 0
    order_attempts: int = 0
    order_rejections: int = 0
    close_window_blocks: int = 0
    model_validation_fails: int = 0

    @property
    def signal_precision(self) -> Optional[float]:
        if self.signal_count == 0:
            return None
        return self.accepted_signals / self.signal_count

    @property
    def order_rejection_rate(self) -> Optional[float]:
        if self.order_attempts == 0:
            return None
        return self.order_rejections / self.order_attempts

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signal_precision"] = self.signal_precision
        d["order_rejection_rate"] = self.order_rejection_rate
        return d


class BaselineMetrics:
    """Accumulates live counters and snapshots them on demand."""

    def __init__(self, phase_label: str = "unset") -> None:
        self.phase_label = phase_label
        self._signal_count = 0
        self._accepted_signals = 0
        self._rejected_signals = 0
        self._net_pnl = 0.0
        self._peak_pnl = 0.0
        self._max_drawdown = 0.0
        self._stale_data_incidents = 0
        self._order_attempts = 0
        self._order_rejections = 0
        self._close_window_blocks = 0
        self._model_validation_fails = 0

    # --- Increment helpers --------------------------------------------------

    def record_signal(self, accepted: bool) -> None:
        self._signal_count += 1
        if accepted:
            self._accepted_signals += 1
        else:
            self._rejected_signals += 1

    def record_pnl(self, delta: float) -> None:
        self._net_pnl += delta
        if self._net_pnl > self._peak_pnl:
            self._peak_pnl = self._net_pnl
        drawdown = self._peak_pnl - self._net_pnl
        if drawdown > self._max_drawdown:
            self._max_drawdown = drawdown

    def record_order(self, rejected: bool) -> None:
        self._order_attempts += 1
        if rejected:
            self._order_rejections += 1

    def record_stale_data(self) -> None:
        self._stale_data_incidents += 1
        log.debug("baseline_stale_data_incident", total=self._stale_data_incidents)

    def record_close_window_block(self) -> None:
        self._close_window_blocks += 1
        log.debug("baseline_close_window_block", total=self._close_window_blocks)

    def record_model_validation_fail(self) -> None:
        self._model_validation_fails += 1
        log.debug("baseline_model_validation_fail", total=self._model_validation_fails)

    # --- Snapshot -----------------------------------------------------------

    def snapshot(self) -> Snapshot:
        snap = Snapshot(
            captured_at=datetime.now(timezone.utc).isoformat(),
            phase_label=self.phase_label,
            signal_count=self._signal_count,
            accepted_signals=self._accepted_signals,
            rejected_signals=self._rejected_signals,
            net_pnl=self._net_pnl,
            peak_pnl=self._peak_pnl,
            max_drawdown=self._max_drawdown,
            stale_data_incidents=self._stale_data_incidents,
            order_attempts=self._order_attempts,
            order_rejections=self._order_rejections,
            close_window_blocks=self._close_window_blocks,
            model_validation_fails=self._model_validation_fails,
        )
        log.info("baseline_snapshot", **snap.to_dict())
        return snap

    def snapshot_to_file(self, path: str) -> None:
        """Write a snapshot to a JSON file for offline comparison."""
        snap = self.snapshot()
        try:
            existing: list[dict[str, Any]] = []
            if os.path.exists(path):
                with open(path, "r") as fh:
                    loaded = json.load(fh)
                    if isinstance(loaded, list):
                        existing = cast(list[dict[str, Any]], loaded)
            existing.append(snap.to_dict())
            with open(path, "w") as fh:
                json.dump(existing, fh, indent=2)
            log.info("baseline_snapshot_written", path=path, phase=self.phase_label)
        except OSError as exc:
            log.error("baseline_snapshot_write_failed", error=str(exc))


# --- Module-level singleton ------------------------------------------------

metrics = BaselineMetrics(phase_label="phase_0_baseline")
