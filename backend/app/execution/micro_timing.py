"""Micro-timing optimization using order book signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class MicroTimingSignal:
    direction_prob: float
    imbalance: float
    spread: float
    recommended_delay_secs: float
    rationale: str


def predict_short_term_direction(order_book: Dict[str, float]) -> MicroTimingSignal:
    bid = order_book.get("best_bid", 0.0)
    ask = order_book.get("best_ask", 0.0)
    bid_sz = order_book.get("bid_size", 1.0)
    ask_sz = order_book.get("ask_size", 1.0)
    spread = max(ask - bid, 1e-4)
    imbalance = (bid_sz - ask_sz) / max(bid_sz + ask_sz, 1e-6)
    flow = order_book.get("trade_sign", 0.0)
    prob_up = 0.5 + 0.25 * imbalance - 0.15 * flow
    prob_up = float(np.clip(prob_up, 0.0, 1.0))
    delay = 1.0 if spread > 0.05 else 0.2
    rationale = "tight_spread" if spread < 0.02 else "wide_spread_wait"
    return MicroTimingSignal(direction_prob=prob_up, imbalance=imbalance, spread=spread, recommended_delay_secs=delay, rationale=rationale)


def optimal_entry_window(signals: List[MicroTimingSignal]) -> Tuple[float, float]:
    if not signals:
        return 0.0, 0.0
    probs = [s.direction_prob for s in signals]
    delays = [s.recommended_delay_secs for s in signals]
    best_idx = int(np.argmax(probs))
    return delays[best_idx], probs[best_idx]


def forecast_liquidity(spread_series: List[float], depth_series: List[float]) -> Dict[str, float]:
    if not spread_series or not depth_series:
        return {"expected_spread": None, "expected_depth": None}
    spread_trend = np.polyfit(np.arange(len(spread_series)), spread_series, deg=1)[0]
    depth_trend = np.polyfit(np.arange(len(depth_series)), depth_series, deg=1)[0]
    expected_spread = float(spread_series[-1] + spread_trend)
    expected_depth = float(depth_series[-1] + depth_trend)
    return {"expected_spread": expected_spread, "expected_depth": expected_depth}
