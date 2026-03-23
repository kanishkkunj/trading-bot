"""Promoter and insider activity tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class InsiderEvent:
    as_of: datetime
    symbol: str
    actor: str  # promoter/insider entity
    action: str  # buy/sell/pledge
    quantity: float
    value: float
    pledge_pct: Optional[float] = None


@dataclass
class PledgeStatus:
    symbol: str
    pledge_pct: float
    trend: float  # change over window


class InsiderTracker:
    """Monitors insider buys/sells, bulk/block deals, and pledges."""

    def __init__(self, window: int = 30, high_pledge: float = 0.4) -> None:
        self.window = window
        self.high_pledge = high_pledge
        self.events: List[InsiderEvent] = []

    def ingest(self, ev: InsiderEvent) -> None:
        self.events.append(ev)
        self.events = self.events[-1000 :]

    def promoter_bias(self, symbol: str) -> str:
        filtered = [e for e in self.events if e.symbol == symbol and e.action in {"buy", "sell"}]
        if not filtered:
            return "neutral"
        buys = sum(e.value for e in filtered if e.action == "buy")
        sells = sum(e.value for e in filtered if e.action == "sell")
        if buys > sells * 1.5:
            return "promoter_accumulation"
        if sells > buys * 1.5:
            return "promoter_distribution"
        return "neutral"

    def pledge_risk(self, symbol: str) -> PledgeStatus:
        pledges = [e for e in self.events if e.symbol == symbol and e.pledge_pct is not None]
        if not pledges:
            return PledgeStatus(symbol=symbol, pledge_pct=0.0, trend=0.0)
        pledges = pledges[-self.window :]
        trend = pledges[-1].pledge_pct - pledges[0].pledge_pct if len(pledges) > 1 else 0.0
        return PledgeStatus(symbol=symbol, pledge_pct=pledges[-1].pledge_pct, trend=trend)

    def bulk_block_pressure(self, symbol: str, notional_threshold: float = 5_000_000) -> str:
        bulk = [e for e in self.events if e.symbol == symbol and e.value >= notional_threshold and e.action in {"buy", "sell"}]
        if not bulk:
            return "neutral"
        buys = sum(e.value for e in bulk if e.action == "buy")
        sells = sum(e.value for e in bulk if e.action == "sell")
        return "bulk_buy" if buys > sells else "bulk_sell"

    def smart_money_flag(self, symbol: str) -> str:
        pledge = self.pledge_risk(symbol)
        bias = self.promoter_bias(symbol)
        if pledge.pledge_pct >= self.high_pledge or pledge.trend > 0.05:
            return "high_pledge_risk"
        return bias
