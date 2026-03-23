"""Kelly and fractional Kelly sizing utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class SignalPerformance:
    wins: int = 0
    losses: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0

    def update(self, pnl: float) -> None:
        if pnl >= 0:
            self.avg_win = (self.avg_win * self.wins + pnl) / max(1, self.wins + 1)
            self.wins += 1
        else:
            pnl_abs = abs(pnl)
            self.avg_loss = (self.avg_loss * self.losses + pnl_abs) / max(1, self.losses + 1)
            self.losses += 1

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total else 0.0

    @property
    def payoff(self) -> float:
        return self.avg_win / max(self.avg_loss, 1e-6) if self.avg_win else 0.0


@dataclass
class KellySizer:
    max_fraction: float = 0.1
    floor_fraction: float = 0.0
    fractional: float = 0.5  # 0.5 = half Kelly
    performances: Dict[str, SignalPerformance] = field(default_factory=dict)

    def record_pnl(self, signal_type: str, pnl: float) -> None:
        perf = self.performances.setdefault(signal_type, SignalPerformance())
        perf.update(pnl)

    def kelly_fraction(self, signal_type: str) -> float:
        perf = self.performances.get(signal_type, SignalPerformance())
        p = perf.win_rate
        b = perf.payoff
        if p == 0 or b == 0:
            return self.floor_fraction
        full_kelly = (p - (1 - p) / b)
        adj = full_kelly * self.fractional
        capped = float(np.clip(adj, self.floor_fraction, self.max_fraction))
        log.debug("kelly", signal=signal_type, full=full_kelly, frac=adj, capped=capped)
        return capped

    def size_position(
        self,
        capital: float,
        signal_type: str,
        recent_drawdown: float = 0.0,
    ) -> float:
        k = self.kelly_fraction(signal_type)
        drawdown_factor = 0.5 if recent_drawdown <= -0.05 else 1.0
        return capital * k * drawdown_factor
