"""Criteria to promote research strategies into paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PromotionCriteria:
    min_sharpe: float = 1.5
    max_drawdown_pct: float = 10.0
    min_win_rate: float = 0.52
    min_trades: int = 50


def eligible(metrics: Dict[str, float], criteria: PromotionCriteria | None = None) -> bool:
    c = criteria or PromotionCriteria()
    if metrics.get("trades", 0) < c.min_trades:
        return False
    if metrics.get("sharpe", 0.0) < c.min_sharpe:
        return False
    if abs(metrics.get("max_drawdown", 0.0)) * 100 > c.max_drawdown_pct:
        return False
    if metrics.get("win_rate", 0.0) < c.min_win_rate:
        return False
    return True
