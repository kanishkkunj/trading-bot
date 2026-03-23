"""Market impact models for execution planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class AlmgrenChrissResult:
    schedule: List[Tuple[float, float]]  # (qty, time_seconds)
    expected_cost: float
    variance: float


class AlmgrenChrissModel:
    """Implements a basic Almgren-Chriss optimal execution schedule."""

    def __init__(self, sigma: float, eta: float, gamma: float, T: float, steps: int = 10) -> None:
        self.sigma = sigma  # volatility
        self.eta = eta  # temporary impact
        self.gamma = gamma  # permanent impact
        self.T = T  # horizon in seconds
        self.steps = steps

    def optimize(self, X: float) -> AlmgrenChrissResult:
        dt = self.T / self.steps
        k = self.gamma / (2 * self.eta)
        lam = (self.sigma**2) * dt / (2 * self.eta)
        weights = [np.sinh(k * (self.T - t * dt)) for t in range(self.steps + 1)]
        norm = sum(weights)
        slice_qty = [X * w / norm for w in weights[:-1]]
        schedule = [(float(q), float(t * dt)) for t, q in enumerate(slice_qty)]
        expected_cost = float(self.gamma * X**2 + self.eta * sum(q**2 for q in slice_qty))
        variance = float((self.sigma**2) * dt * sum((X - sum(slice_qty[:i]))**2 for i in range(1, len(slice_qty) + 1)))
        return AlmgrenChrissResult(schedule=schedule, expected_cost=expected_cost, variance=variance)


@dataclass
class KissellResult:
    expected_cost_bps: float
    timing_risk_bps: float
    liquidity_score: float


class KissellModel:
    """Simplified Kissell Research adaptation for Indian markets."""

    def __init__(self, country_factor: float = 1.1) -> None:
        self.country_factor = country_factor

    def estimate(self, pct_adv: float, volatility: float, spread_bps: float) -> KissellResult:
        liquidity_score = float(max(0.1, 1 - pct_adv * 5))
        market_impact = float(pct_adv * (spread_bps / 10000) * self.country_factor)
        timing_risk = float(volatility * np.sqrt(pct_adv) * self.country_factor)
        expected_cost_bps = (market_impact + timing_risk) * 10000
        return KissellResult(expected_cost_bps=expected_cost_bps, timing_risk_bps=timing_risk * 10000, liquidity_score=liquidity_score)


def realtime_impact(pct_adv: float, spread: float, volatility: float) -> Dict[str, float]:
    """Estimate instantaneous impact based on size vs ADV and current microstructure."""
    impact = pct_adv * (spread + volatility * 0.5)
    adverse = max(0.0, (pct_adv - 0.05) * volatility)
    return {"impact": float(impact), "adverse_risk": float(adverse)}
