"""Slippage and adverse selection modeling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np


@dataclass
class SlippageEstimate:
    expected_bps: float
    variance_bps: float
    adverse_selection_prob: float


class SlippageModel:
    """Estimate and analyze execution slippage."""

    def __init__(self, base_spread_bps: float = 5.0) -> None:
        self.base_spread_bps = base_spread_bps

    def estimate(self, volatility: float, spread_bps: float, pct_adv: float, time_of_day: float) -> SlippageEstimate:
        spread = max(spread_bps, self.base_spread_bps)
        vol_component = volatility * 10000 * 0.5
        size_component = pct_adv * spread * 2
        tod_component = (0.5 if time_of_day in (0, 1) else 1.0) * spread
        expected = spread + vol_component + size_component + tod_component
        variance = (volatility * 10000) ** 2 * 0.1
        adverse = float(np.clip(0.2 + 2 * pct_adv + 0.1 * (volatility > 0.02), 0.0, 0.95))
        return SlippageEstimate(expected_bps=float(expected), variance_bps=float(variance), adverse_selection_prob=adverse)

    def adverse_selection(self, trade_direction: str, short_term_signal: float) -> float:
        direction = 1 if trade_direction.upper() == "BUY" else -1
        prob = 0.5 - 0.3 * direction * short_term_signal
        return float(np.clip(prob, 0.0, 1.0))

    def post_trade_report(self, arrival_price: float, fills: List[Dict[str, float]]) -> Dict[str, float]:
        if not fills:
            return {"slippage_bps": None, "implementation_shortfall": None}
        qty_total = sum(f.get("qty", 0.0) for f in fills)
        if qty_total == 0:
            return {"slippage_bps": None, "implementation_shortfall": None}
        vwap_fill = sum(f.get("price", 0.0) * f.get("qty", 0.0) for f in fills) / qty_total
        side = 1 if fills[0].get("side", "BUY").upper() == "BUY" else -1
        slippage = (vwap_fill - arrival_price) * side / arrival_price * 10000
        shortfall = (vwap_fill - arrival_price) * side * qty_total
        return {"slippage_bps": float(slippage), "implementation_shortfall": float(shortfall)}
