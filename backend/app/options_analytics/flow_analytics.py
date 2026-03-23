"""Options flow analytics: unusual activity, sweeps, skew, IVR/IVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class FlowMetrics:
    """Key flow metrics used by signals and trading filters."""

    pct_unusual: float
    whale_trades: int
    sweep_trades: int
    put_call_ratio: float
    skew_momentum: float
    iv_rank: float
    iv_percentile: float
    bullish_flow_ratio: float


class FlowAnalytics:
    """Detects unusual options activity and summarizes flow."""

    def __init__(self, vol_lookback: int = 20, whale_notional: float = 5_000_000) -> None:
        self.vol_lookback = vol_lookback
        self.whale_notional = whale_notional

    def unusual_volume(self, vols: List[float]) -> np.ndarray:
        arr = np.asarray(vols, dtype=float)
        if arr.size < 2:
            return np.zeros_like(arr)
        mean = arr[-self.vol_lookback :].mean()
        std = arr[-self.vol_lookback :].std() + 1e-6
        zscores = (arr - mean) / std
        return zscores

    def detect_whales(self, trades: List[Dict]) -> int:
        return sum(1 for t in trades if t.get("notional", 0) >= self.whale_notional)

    def detect_sweeps(self, trades: List[Dict]) -> int:
        """Identify rapid multi-venue buys (heuristic)."""
        sweeps = 0
        trades_sorted = sorted(trades, key=lambda x: x.get("ts", 0))
        window = []
        for t in trades_sorted:
            window = [w for w in window if t.get("ts", 0) - w.get("ts", 0) <= 2]
            window.append(t)
            venues = {w.get("venue") for w in window}
            sides = {w.get("side") for w in window}
            if len(window) >= 3 and len(venues) >= 2 and sides == {"BUY"}:
                sweeps += 1
        return sweeps

    def put_call_skew(self, puts_iv: float, calls_iv: float, prev_skew: float | None = None) -> Tuple[float, float]:
        skew = puts_iv - calls_iv
        momentum = skew - (prev_skew or 0.0)
        return skew, momentum

    def iv_rank_percentile(self, iv: float, history: List[float]) -> Tuple[float, float]:
        hist = np.asarray(history, dtype=float)
        if hist.size == 0:
            return 0.0, 0.0
        iv_rank = (iv - hist.min()) / (hist.max() - hist.min() + 1e-6)
        iv_percentile = float((hist < iv).mean())
        return float(iv_rank), iv_percentile

    def summarize_flow(
        self,
        vols: List[float],
        trades: List[Dict],
        puts_iv: float,
        calls_iv: float,
        iv_history: List[float],
        bullish_notional: float,
        bearish_notional: float,
        prev_skew: float | None = None,
    ) -> FlowMetrics:
        zscores = self.unusual_volume(vols)
        whale_trades = self.detect_whales(trades)
        sweep_trades = self.detect_sweeps(trades)
        skew, skew_momentum = self.put_call_skew(puts_iv, calls_iv, prev_skew)
        iv_rank, iv_percentile = self.iv_rank_percentile((puts_iv + calls_iv) / 2, iv_history)
        total_flow = bullish_notional + bearish_notional + 1e-6
        bullish_ratio = bullish_notional / total_flow
        put_call_ratio = bearish_notional / total_flow
        return FlowMetrics(
            pct_unusual=float((zscores > 3).mean()) if zscores.size else 0.0,
            whale_trades=whale_trades,
            sweep_trades=sweep_trades,
            put_call_ratio=float(put_call_ratio),
            skew_momentum=float(skew_momentum),
            iv_rank=float(iv_rank),
            iv_percentile=float(iv_percentile),
            bullish_flow_ratio=float(bullish_ratio),
        )
