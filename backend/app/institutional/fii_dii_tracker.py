"""FII/DII flow ingestion and trend analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np


@dataclass
class FlowSnapshot:
    as_of: datetime
    fii_cash: float
    fii_futures: float
    dii_cash: float
    dii_futures: float
    sector_flows: Dict[str, float]


@dataclass
class FlowTrends:
    trend_fii: float
    trend_dii: float
    sector_changes: Dict[str, float]
    cash_fut_shift: float


class FiiDiiTracker:
    """Tracks daily FII/DII flows and computes trends."""

    def __init__(self, lookback: int = 30) -> None:
        self.lookback = lookback
        self.history: List[FlowSnapshot] = []

    def ingest(self, snap: FlowSnapshot) -> None:
        self.history.append(snap)
        self.history = self.history[-self.lookback :]

    def trend(self) -> FlowTrends:
        if not self.history:
            return FlowTrends(0.0, 0.0, {}, 0.0)
        fii = np.array([h.fii_cash + h.fii_futures for h in self.history], dtype=float)
        dii = np.array([h.dii_cash + h.dii_futures for h in self.history], dtype=float)
        trend_fii = float(fii[-1] - fii[0]) if fii.size > 1 else 0.0
        trend_dii = float(dii[-1] - dii[0]) if dii.size > 1 else 0.0
        sector_changes: Dict[str, float] = {}
        latest = self.history[-1].sector_flows
        first = self.history[0].sector_flows if self.history else {}
        for sec, val in latest.items():
            sector_changes[sec] = val - first.get(sec, 0.0)
        cash_fut_shift = float((self.history[-1].fii_cash - self.history[-1].fii_futures))
        return FlowTrends(trend_fii=trend_fii, trend_dii=trend_dii, sector_changes=sector_changes, cash_fut_shift=cash_fut_shift)

    def smart_money_signal(self) -> str:
        t = self.trend()
        if t.trend_fii > 0 and t.trend_dii > 0:
            return "broad_accumulation"
        if t.trend_fii > 0 and t.trend_dii < 0:
            return "fii_buy_dii_sell"
        if t.trend_fii < 0 and t.trend_dii > 0:
            return "dii_defensive"
        return "neutral"

    def sector_bias(self, top_n: int = 3) -> List[str]:
        if not self.history:
            return []
        latest = self.history[-1].sector_flows
        return [k for k, _ in sorted(latest.items(), key=lambda x: x[1], reverse=True)[:top_n]]
