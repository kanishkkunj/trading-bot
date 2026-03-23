"""Dynamic risk limits and scaling rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import structlog

log = structlog.get_logger()


@dataclass
class DrawdownRules:
    reduce_at: float = -0.05
    halt_at: float = -0.10
    reduce_factor: float = 0.5


@dataclass
class RiskLimits:
    daily_loss_limit: float
    drawdown_rules: DrawdownRules = field(default_factory=DrawdownRules)
    corr_limit: float = 0.7
    sector_limit: float = 0.2
    correlated_sector_limit: float = 0.4


class LimitChecker:
    """Checks and scales positions according to dynamic risk limits."""

    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits
        self.daily_pnl = 0.0
        self.cool_off = False

    def record_pnl(self, pnl: float) -> None:
        self.daily_pnl += pnl
        if self.daily_pnl <= -abs(self.limits.daily_loss_limit):
            self.cool_off = True
            log.warning("daily_loss_limit_hit", pnl=self.daily_pnl)

    def scale_for_drawdown(self, cumulative_pnl: float, position: float) -> float:
        if cumulative_pnl <= self.limits.drawdown_rules.halt_at:
            return 0.0
        if cumulative_pnl <= self.limits.drawdown_rules.reduce_at:
            return position * self.limits.drawdown_rules.reduce_factor
        return position

    def check_correlation_limit(self, portfolio_corr: float, position: float) -> float:
        if portfolio_corr > self.limits.corr_limit:
            return position * 0.5
        return position

    def check_sector_limits(self, sector_weights: Dict[str, float]) -> Dict[str, float]:
        adjustments = {}
        for sector, weight in sector_weights.items():
            if weight > self.limits.sector_limit:
                adjustments[sector] = self.limits.sector_limit / weight
            elif weight > self.limits.correlated_sector_limit:
                adjustments[sector] = self.limits.correlated_sector_limit / weight
        return adjustments

    def allow_new_trades(self) -> bool:
        return not self.cool_off
