"""Options-derived signals and integration utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.options_analytics.flow_analytics import FlowAnalytics, FlowMetrics, OIFeatures


@dataclass
class GammaExposure:
    strike: float
    gamma: float


class OptionsSignals:
    """Generates predictive signals from options surface and flow."""

    def __init__(self, flow_analytics: FlowAnalytics | None = None) -> None:
        self.flow = flow_analytics or FlowAnalytics()

    def flow_sentiment(self, flow: FlowMetrics) -> float:
        """Bullish minus bearish share of flow ([-1, 1])."""
        return float(2 * flow.bullish_flow_ratio - 1)

    def gamma_exposure(self, chain: List[Dict]) -> Tuple[float, List[GammaExposure]]:
        """Aggregate gamma by strike to find pin risk (max absolute gamma)."""
        gamma_by_strike: Dict[float, float] = {}
        for c in chain:
            strike = float(c.get("strike"))
            gamma_val = float(c.get("gamma", 0) or 0)
            size = float(c.get("open_interest", 0) or 0)
            gamma_by_strike[strike] = gamma_by_strike.get(strike, 0.0) + gamma_val * size
        exposures = [GammaExposure(k, v) for k, v in gamma_by_strike.items()]
        if not exposures:
            return 0.0, []
        max_pin = max(exposures, key=lambda g: abs(g.gamma)).strike
        return max_pin, exposures

    def max_pain(self, chain: List[Dict]) -> float:
        """Compute max pain price (min payout to option holders)."""
        strikes = sorted({float(c.get("strike")) for c in chain})
        if not strikes:
            return 0.0
        payouts = []
        for strike in strikes:
            payoff = 0.0
            for c in chain:
                k = float(c.get("strike"))
                oi = float(c.get("open_interest", 0) or 0)
                typ = c.get("option_type", "CALL")
                if typ == "CALL":
                    payoff += max(0.0, strike - k) * oi
                else:
                    payoff += max(0.0, k - strike) * oi
            payouts.append((strike, payoff))
        return min(payouts, key=lambda x: x[1])[0]

    def volatility_risk_premium(self, realized: float, implied: float) -> float:
        return float(implied - realized)

    def filter_trades(self, trades: List[Dict], flow: FlowMetrics, pcr_threshold: float = 1.2) -> List[Dict]:
        """Drop trades when put/call ratio is spiking beyond threshold."""
        if flow.put_call_ratio > pcr_threshold:
            return []
        return trades

    def confirm_trades(self, trades: List[Dict], flow: FlowMetrics, min_bullish: float = 0.55) -> List[Dict]:
        """Keep only trades aligned with bullish flow for long bias."""
        if not trades:
            return trades
        if flow.bullish_flow_ratio >= min_bullish:
            return trades
        return []

    def expiry_timing_bias(self, as_of: datetime, expiry: datetime, window_days: int = 3) -> float:
        """Return timing bias close to expiry (1 near expiry, 0 otherwise)."""
        days = (expiry - as_of).days
        return float(max(0.0, window_days - abs(days)) / window_days)

    # ------------------------------------------------------------------ OI signals

    def oi_pressure_signal(self, oi_features: OIFeatures) -> float:
        """Directional signal from OI pressure in the ATM neighbourhood.

        Returns a value in [-1, +1]:
          +1  — strong call-OI dominance (bullish bias; market makers short calls,
                supporting near-term upside continuation)
          -1  — strong put-OI dominance (bearish bias; support wall pressure or
                bearish hedging activity)

        The signal is gated by options_signals_enabled() so production scoring
        behaviour is unchanged until the flag is turned on.
        """
        from app.core.feature_flags import options_signals_enabled

        if not options_signals_enabled():
            return 0.0

        return float(np.clip(oi_features.oi_weighted_bias, -1.0, 1.0))

    def boundary_proximity_signal(self, spot: float, oi_features: OIFeatures) -> Tuple[float, float]:
        """Return (call_proximity, put_proximity) as fractions in [0, 1].

        A value near 1.0 means spot is *close* to the respective wall.
        This is useful for position-sizing and exit-timing decisions: being
        near the call wall in a long trade, or near the put wall in a short
        trade, is a natural profit-taking zone.
        """
        from app.core.feature_flags import options_signals_enabled

        if not options_signals_enabled():
            return 0.0, 0.0

        # Normalise distance: wall 5% away → proximity ~0, wall 0% away → 1.0
        max_pct = 0.05
        call_prox = max(0.0, 1.0 - oi_features.call_wall_distance / max_pct) if oi_features.call_wall_strike > 0 else 0.0
        put_prox = max(0.0, 1.0 - oi_features.put_wall_distance / max_pct) if oi_features.put_wall_strike > 0 else 0.0
        return float(np.clip(call_prox, 0.0, 1.0)), float(np.clip(put_prox, 0.0, 1.0))

    def options_context_summary(
        self,
        oi_features: Optional[OIFeatures],
        flow: Optional[FlowMetrics],
    ) -> Dict[str, float]:
        """Produce a flat feature dict suitable for injection into the Claude payload.

        Only populated when options_signals_enabled(); returns empty dict otherwise
        so legacy callers receive zero new tokens in their prompts.
        """
        from app.core.feature_flags import options_signals_enabled

        if not options_signals_enabled():
            return {}

        result: Dict[str, float] = {}
        if oi_features is not None:
            result["oi_pressure_ratio"] = oi_features.oi_pressure_ratio
            result["oi_weighted_bias"] = oi_features.oi_weighted_bias
            result["call_wall_distance_pct"] = oi_features.call_wall_distance * 100
            result["put_wall_distance_pct"] = oi_features.put_wall_distance * 100
            result["oi_pressure_signal"] = self.oi_pressure_signal(oi_features)
            call_prox, put_prox = self.boundary_proximity_signal(0.0, oi_features)
            result["call_wall_proximity"] = call_prox
            result["put_wall_proximity"] = put_prox
        if flow is not None:
            result["flow_put_call_ratio"] = flow.put_call_ratio
            result["flow_bullish_ratio"] = flow.bullish_flow_ratio
            result["flow_iv_rank"] = flow.iv_rank
        return result


class OptionsBacktester:
    """Simple backtester for options-based signals."""

    def __init__(self) -> None:
        self.pnl: List[float] = []

    def backtest_flow_signal(
        self,
        flows: List[FlowMetrics],
        returns: List[float],
        threshold: float = 0.55,
    ) -> Dict[str, float]:
        pnl = []
        for f, r in zip(flows, returns):
            pos = 1 if f.bullish_flow_ratio >= threshold else -1
            pnl.append(pos * r)
        pnl_arr = np.asarray(pnl, dtype=float)
        return {
            "avg_return": float(pnl_arr.mean()) if pnl_arr.size else 0.0,
            "hit_ratio": float((pnl_arr > 0).mean()) if pnl_arr.size else 0.0,
            "sharpe": float(pnl_arr.mean() / (pnl_arr.std() + 1e-6)) if pnl_arr.size else 0.0,
        }

    def backtest_vrp_signal(self, vrp: List[float], returns: List[float], quantile: float = 0.7) -> Dict[str, float]:
        pnl = []
        cut = np.quantile(vrp, quantile) if vrp else 0.0
        for premium, ret in zip(vrp, returns):
            pos = 1 if premium > cut else 0
            pnl.append(pos * ret)
        pnl_arr = np.asarray(pnl, dtype=float)
        return {
            "avg_return": float(pnl_arr.mean()) if pnl_arr.size else 0.0,
            "hit_ratio": float((pnl_arr > 0).mean()) if pnl_arr.size else 0.0,
            "sharpe": float(pnl_arr.mean() / (pnl_arr.std() + 1e-6)) if pnl_arr.size else 0.0,
        }
