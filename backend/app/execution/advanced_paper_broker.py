"""Advanced paper broker simulating microstructure effects."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class SimFill:
    price: float
    qty: float
    side: str
    liquidity_flag: str = "T"  # maker/taker flag placeholder


@dataclass
class QueueState:
    position: float
    ahead_qty: float
    behind_qty: float


class AdvancedPaperBroker:
    """Simulates queue position, partial fills, and MM reaction."""

    def __init__(self, slippage_model: Any = None) -> None:
        self.slippage_model = slippage_model

    def simulate_order(
        self,
        side: str,
        qty: float,
        best_bid: float,
        best_ask: float,
        spread: float,
        depth: float,
        volatility: float,
        time_of_day: float,
    ) -> Tuple[List[SimFill], QueueState, Dict[str, float]]:
        queue = self._queue_position(qty, depth)
        fills = self._partial_fills(side, qty, best_bid, best_ask, spread, queue)
        metrics = self._report(best_bid, best_ask, fills, volatility, spread, qty, time_of_day)
        return fills, queue, metrics

    @staticmethod
    def _queue_position(qty: float, depth: float) -> QueueState:
        ahead = max(0.0, depth * random.uniform(0.2, 0.8))
        behind = max(0.0, depth - ahead - qty)
        return QueueState(position=ahead + qty, ahead_qty=ahead, behind_qty=behind)

    def _partial_fills(
        self, side: str, qty: float, bid: float, ask: float, spread: float, queue: QueueState
    ) -> List[SimFill]:
        remaining = qty
        fills: list[SimFill] = []
        price = bid if side.upper() == "SELL" else ask
        while remaining > 0:
            prob_fill = min(0.9, max(0.1, queue.ahead_qty / max(queue.position, 1e-6)))
            if random.random() < prob_fill:
                clip = remaining * random.uniform(0.2, 0.6)
                fills.append(SimFill(price=price, qty=clip, side=side))
                remaining -= clip
                queue.ahead_qty = max(0.0, queue.ahead_qty - clip)
            else:
                # Market makers pull liquidity -> widen spread and reduce fill chance
                price += spread * 0.25 if side.upper() == "BUY" else -spread * 0.25
                queue.ahead_qty += remaining * 0.1
            if len(fills) > 20:  # safety
                break
        return fills

    def _report(
        self,
        bid: float,
        ask: float,
        fills: List[SimFill],
        volatility: float,
        spread: float,
        qty: float,
        time_of_day: float,
    ) -> Dict[str, float]:
        metrics = {"arrival_price": (bid + ask) / 2, "fill_qty": sum(f.qty for f in fills)}
        if self.slippage_model:
            estimate = self.slippage_model.estimate(volatility=volatility, spread_bps=spread * 10000, pct_adv=qty / max(1e-6, qty * 50), time_of_day=time_of_day)
            report = self.slippage_model.post_trade_report(metrics["arrival_price"], [f.__dict__ for f in fills])
            metrics.update({"expected_slippage_bps": estimate.expected_bps, **report})
        return metrics
