"""Tail-risk hedging rules and scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import structlog

log = structlog.get_logger()

# Hard-block threshold — mirrors the MiroFish TAIL_RISK_SCORE threshold in the n8n workflow.
# Scores at or above this level cause pre-trade checks to hard-reject new entries.
TAIL_RISK_BLOCK_THRESHOLD: float = 0.70

# VIX levels used to normalise the score component
_VIX_LOW = 12.0
_VIX_HIGH = 35.0


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

    def compute_score(
        self,
        india_vix: float,
        vol_forecast: float,
        oi_pressure_ratio: Optional[float] = None,
    ) -> float:
        """Return a tail risk score in [0, 1].

        A score >= TAIL_RISK_BLOCK_THRESHOLD (0.70) causes pre-trade hard blocks.

        Components:
          - VIX component (40% weight): linearly scaled between _VIX_LOW and _VIX_HIGH
          - Vol forecast component (40% weight): scaled at 0.30 = full spike
          - OI pressure component (20% weight, when available): put-heavy chains
            signal hedging demand which can amplify tail risk
        """
        vix_norm = min(1.0, max(0.0, (india_vix - _VIX_LOW) / (_VIX_HIGH - _VIX_LOW)))
        vol_norm = min(1.0, max(0.0, vol_forecast / 0.30))

        if oi_pressure_ratio is not None:
            # oi_pressure_ratio > 1 means bearish/put pressure; clip to [0, 3] then scale
            oi_norm = min(1.0, max(0.0, (oi_pressure_ratio - 1.0) / 2.0))
            score = 0.40 * vix_norm + 0.40 * vol_norm + 0.20 * oi_norm
        else:
            # Redistribute OI weight back to VIX and vol equally
            score = 0.50 * vix_norm + 0.50 * vol_norm

        score = float(min(1.0, max(0.0, score)))
        log.debug(
            "tail_risk_score",
            india_vix=india_vix,
            vol_forecast=vol_forecast,
            oi_pressure_ratio=oi_pressure_ratio,
            score=round(score, 4),
        )
        return score

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
