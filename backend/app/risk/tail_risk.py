"""Tail-risk hedging rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import structlog

log = structlog.get_logger()


@dataclass
class TailHedgeDecision:
    action: str
    notionals: Dict[str, float]
    rationale: str


@dataclass
class TailRiskRules:
    vix_trigger: float = 25.0
    vol_spike_pct: float = 0.2
    max_hedge_notional: float = 0.2  # % of portfolio


class TailRiskHedger:
    """Creates hedge actions based on volatility signals."""

    def __init__(self, rules: TailRiskRules | None = None) -> None:
        self.rules = rules or TailRiskRules()

    def decide(
        self,
        portfolio_value: float,
        india_vix: float,
        vol_forecast: float,
        base_symbol: str = "NIFTY",
    ) -> TailHedgeDecision:
        if india_vix >= self.rules.vix_trigger or vol_forecast >= self.rules.vol_spike_pct:
            notional = portfolio_value * self.rules.max_hedge_notional
            return TailHedgeDecision(
                action="buy_put_spread",
                notionals={f"{base_symbol}_puts": notional},
                rationale="vol_spike",
            )
        return TailHedgeDecision(action="hold", notionals={}, rationale="no_hedge")
