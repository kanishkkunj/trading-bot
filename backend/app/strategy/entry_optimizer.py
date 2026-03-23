"""Entry optimization with confluence and staged sizing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class EntryDecision:
    proceed: bool
    rationale: str
    stages: List[Tuple[float, float]]  # (fraction, trigger_level)
    delay_seconds: float = 0.0


class EntryOptimizer:
    """Enforces confluence and staged entries."""

    def __init__(self, min_signals: int = 2, max_correlation: float = 0.6) -> None:
        self.min_signals = min_signals
        self.max_corr = max_correlation

    def require_confluence(self, signals: Dict[str, float], correlations: Dict[Tuple[str, str], float]) -> bool:
        active = [s for s, v in signals.items() if v]
        if len(active) < self.min_signals:
            return False
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                pair = (active[i], active[j])
                corr = correlations.get(pair) or correlations.get((pair[1], pair[0]))
                if corr is not None and corr > self.max_corr:
                    return False
        return True

    def timing_rules(
        self,
        setup: str,
        trend: float,
        pullback_pct: float,
        breakout_level: Optional[float],
        current_price: float,
    ) -> Tuple[bool, float]:
        setup = setup.lower()
        if setup == "pullback_uptrend":
            return trend > 0 and pullback_pct >= 0.01, 0.0
        if setup == "breakout":
            if breakout_level and current_price > breakout_level:
                return True, 0.0
            return False, 0.0
        return True, 0.0

    def stage_sizing(self, base_size: float) -> List[Tuple[float, float]]:
        return [(0.3 * base_size, 0.0), (0.4 * base_size, 1.0), (0.3 * base_size, 2.0)]

    def decide(
        self,
        signals: Dict[str, float],
        correlations: Dict[Tuple[str, str], float],
        setup: str,
        trend: float,
        pullback_pct: float,
        breakout_level: Optional[float],
        current_price: float,
        base_size: float,
    ) -> EntryDecision:
        if not self.require_confluence(signals, correlations):
            return EntryDecision(False, "insufficient_confluence", [])
        ok, delay = self.timing_rules(setup, trend, pullback_pct, breakout_level, current_price)
        if not ok:
            return EntryDecision(False, "timing_not_met", [])
        stages = self.stage_sizing(base_size)
        return EntryDecision(True, "entry_ok", stages, delay_seconds=delay)
