"""Dynamic exit management with trailing stops, profit targets, and regime logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class ExitPlan:
    stop: float
    targets: Dict[float, float]  # price -> fraction to exit
    time_stop_days: Optional[int]
    rationale: str


class ExitManager:
    """Manage exits with ATR trails, multi-targets, and regime adjustments."""

    def __init__(self, atr_multiple: float = 3.0, accel: float = 0.5) -> None:
        self.atr_multiple = atr_multiple
        self.accel = accel

    def trailing_stop(self, entry: float, atr: float, pnl_multiple: float) -> float:
        tighten = max(0.5, 1 - self.accel * pnl_multiple)
        return entry - atr * self.atr_multiple * tighten

    def targets(self, entry: float, risk: float) -> Dict[float, float]:
        return {
            entry + 2 * risk: 0.3,
            entry + 3 * risk: 0.3,
            entry + 5 * risk: 0.2,
        }

    def regime_adjust(self, regime: str, stop: float, targets: Dict[float, float]) -> Tuple[float, Dict[float, float]]:
        if regime in {"high_vol", "crisis"}:
            stop = stop + (abs(stop) * 0.1)
            targets = {k: v for k, v in targets.items() if k <= list(targets.keys())[-1]}
        return stop, targets

    def plan(
        self,
        entry: float,
        atr: float,
        risk: float,
        pnl_multiple: float,
        regime: str,
        time_stop_days: int = 3,
        opposite_signal: Optional[float] = None,
    ) -> ExitPlan:
        stop = self.trailing_stop(entry, atr, pnl_multiple)
        tgt = self.targets(entry, risk)
        stop, tgt = self.regime_adjust(regime, stop, tgt)
        rationale = "standard"
        if opposite_signal and opposite_signal > 0.7:
            rationale = "opposite_signal"
        return ExitPlan(stop=float(stop), targets=tgt, time_stop_days=time_stop_days, rationale=rationale)
