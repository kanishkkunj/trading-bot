"""Options flow analytics: unusual activity, sweeps, skew, IVR/IVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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


@dataclass
class OIFeatures:
    """Open-interest derived features for a single underlying snapshot.

    Inspired by the NSE option-chain boundary/pressure methodology from Repo 1,
    but implemented independently using only our own data structures.
    """

    # Strike carrying the highest cumulative call OI (acts as near-term resistance)
    call_wall_strike: float
    # Strike carrying the highest cumulative put OI (acts as near-term support)
    put_wall_strike: float
    # Total call OI within ATM neighbourhood (defined by atm_pct radius)
    atm_call_oi: float
    # Total put OI within ATM neighbourhood
    atm_put_oi: float
    # put / call OI ratio in the ATM zone (>1 → put-heavy / bearish pressure)
    oi_pressure_ratio: float
    # OI-weighted directional bias [-1 (bearish) .. +1 (bullish)]
    oi_weighted_bias: float
    # Distance of spot from call wall as fraction of spot (positive = below wall)
    call_wall_distance: float
    # Distance of spot from put wall as fraction of spot (positive = above wall)
    put_wall_distance: float


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

    # ---------------------------------------------------------------------- OI features

    def oi_boundary_strikes(
        self,
        calls: List[Dict],
        puts: List[Dict],
    ) -> Tuple[float, float]:
        """Find the call wall (max call OI) and put wall (max put OI) strikes.

        These strikes act as near-term resistance and support boundaries
        respectively — large option writers tend to defend them.

        Returns (call_wall_strike, put_wall_strike).  Returns (0.0, 0.0) when
        the chain is empty (e.g. outside market hours).
        """
        if not calls and not puts:
            return 0.0, 0.0

        call_wall = max(calls, key=lambda r: float(r.get("openInterest") or 0), default=None)
        put_wall = max(puts, key=lambda r: float(r.get("openInterest") or 0), default=None)
        return (
            float(call_wall.get("strike", 0.0)) if call_wall else 0.0,
            float(put_wall.get("strike", 0.0)) if put_wall else 0.0,
        )

    def oi_features(
        self,
        calls: List[Dict],
        puts: List[Dict],
        spot: float,
        atm_pct: float = 0.02,
    ) -> Optional[OIFeatures]:
        """Compute OI boundary + pressure features for a single expiry slice.

        Args:
            calls:    List of call option records from yfinance option_chain.
            puts:     List of put option records.
            spot:     Current underlying price.
            atm_pct:  Radius around spot (as fraction) for ATM neighbourhood.

        Returns None when the chain is too sparse to compute meaningful features.
        """
        if not calls or not puts or spot <= 0:
            return None

        call_wall_strike, put_wall_strike = self.oi_boundary_strikes(calls, puts)

        low = spot * (1.0 - atm_pct)
        high = spot * (1.0 + atm_pct)
        atm_call_oi = sum(
            float(r.get("openInterest") or 0)
            for r in calls
            if low <= float(r.get("strike", 0.0)) <= high
        )
        atm_put_oi = sum(
            float(r.get("openInterest") or 0)
            for r in puts
            if low <= float(r.get("strike", 0.0)) <= high
        )

        oi_pressure_ratio = atm_put_oi / (atm_call_oi + 1.0)

        # Weighted bias: +1 when calls dominate, -1 when puts dominate
        total_atm_oi = atm_call_oi + atm_put_oi + 1e-6
        oi_weighted_bias = (atm_call_oi - atm_put_oi) / total_atm_oi

        call_wall_distance = (call_wall_strike - spot) / spot if call_wall_strike > 0 else 0.0
        put_wall_distance = (spot - put_wall_strike) / spot if put_wall_strike > 0 else 0.0

        return OIFeatures(
            call_wall_strike=call_wall_strike,
            put_wall_strike=put_wall_strike,
            atm_call_oi=atm_call_oi,
            atm_put_oi=atm_put_oi,
            oi_pressure_ratio=oi_pressure_ratio,
            oi_weighted_bias=oi_weighted_bias,
            call_wall_distance=call_wall_distance,
            put_wall_distance=put_wall_distance,
        )

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
