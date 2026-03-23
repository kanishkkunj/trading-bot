"""Mutual fund holdings tracking and crowded-trade detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class HoldingsSnapshot:
    fund: str
    symbol_weights: Dict[str, float]  # symbol -> weight


@dataclass
class CrowdedTrade:
    symbol: str
    fund_count: int
    avg_weight: float


class FundHoldingsTracker:
    """Tracks holdings changes and flags crowded trades."""

    def __init__(self) -> None:
        self.history: List[HoldingsSnapshot] = []

    def ingest(self, snap: HoldingsSnapshot) -> None:
        self.history.append(snap)
        self.history = self.history[-100 :]

    def crowded_trades(self, min_funds: int = 5, weight_cut: float = 0.02) -> List[CrowdedTrade]:
        if not self.history:
            return []
        counts: Dict[str, List[float]] = {}
        for snap in self.history:
            for sym, w in snap.symbol_weights.items():
                if w < weight_cut:
                    continue
                counts.setdefault(sym, []).append(w)
        crowded: List[CrowdedTrade] = []
        for sym, weights in counts.items():
            if len(weights) >= min_funds:
                crowded.append(CrowdedTrade(symbol=sym, fund_count=len(weights), avg_weight=sum(weights) / len(weights)))
        return crowded

    def holdings_change(self, prev: HoldingsSnapshot, curr: HoldingsSnapshot) -> Dict[str, float]:
        delta: Dict[str, float] = {}
        for sym, w in curr.symbol_weights.items():
            delta[sym] = w - prev.symbol_weights.get(sym, 0.0)
        return delta

    def smart_money_signals(self, fii_bias: str, dii_bias: str, promoter_bias: str) -> str:
        """Combine fund crowding with external flows for confluence."""
        if promoter_bias == "promoter_accumulation" and fii_bias.startswith("fii"):
            return "strong_buy_signal"
        if fii_bias == "fii_buy_dii_sell" and dii_bias == "dii_defensive":
            return "contrarian_long_on_dii_selling"
        if promoter_bias == "promoter_distribution":
            return "avoid_or_short"
        return "neutral"
