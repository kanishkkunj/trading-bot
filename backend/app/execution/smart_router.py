"""Smart order router with venue selection, internal crossing, and algo choice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class VenueQuote:
    venue: str
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    fee_bps: float = 0.0
    latency_ms: float = 5.0


@dataclass
class RouteDecision:
    venue: str
    algo: str
    slices: List[Tuple[float, float]]  # list of (qty, target_time_seconds)
    internal_cross_qty: float = 0.0
    notes: Optional[str] = None


class SmartOrderRouter:
    """Route orders to optimal venue and execution algorithm."""

    def __init__(self, risk_checker: Optional[Any] = None) -> None:
        self.risk_checker = risk_checker

    def route_order(
        self,
        side: str,
        quantity: float,
        symbol: str,
        arrival_price: float,
        urgency: str,
        venue_quotes: List[VenueQuote],
        internal_orders: Optional[List[Dict[str, Any]]] = None,
        adv: Optional[float] = None,
    ) -> RouteDecision:
        self._pre_trade_check(symbol, side, quantity, arrival_price)
        internal_cross = self._internal_cross(side, quantity, internal_orders or [])
        remaining_qty = max(0.0, quantity - internal_cross)

        best_venue = self._select_venue(side, remaining_qty, venue_quotes)
        algo = self._select_algo(urgency=urgency, adv=adv, qty=remaining_qty)
        slices = self._slice_order(algo, remaining_qty)
        notes = f"internal_cross={internal_cross}" if internal_cross > 0 else None
        return RouteDecision(venue=best_venue, algo=algo, slices=slices, internal_cross_qty=internal_cross, notes=notes)

    def _pre_trade_check(self, symbol: str, side: str, qty: float, price: float) -> None:
        if not self.risk_checker:
            return
        allowed, reason = self.risk_checker.check(symbol=symbol, side=side, quantity=qty, price=price)
        if not allowed:
            raise RuntimeError(f"Risk check failed: {reason}")

    @staticmethod
    def _internal_cross(side: str, qty: float, internal_orders: List[Dict[str, Any]]) -> float:
        opposing = "SELL" if side.upper() == "BUY" else "BUY"
        matchable = [o for o in internal_orders if o.get("side") == opposing]
        available = sum(float(o.get("quantity", 0)) for o in matchable)
        cross_qty = min(qty, available)
        if cross_qty > 0:
            log.info("internal_cross", qty=cross_qty)
        return cross_qty

    @staticmethod
    def _select_venue(side: str, qty: float, quotes: List[VenueQuote]) -> str:
        if not quotes:
            raise RuntimeError("No venue quotes available")
        scores = []
        for q in quotes:
            spread = q.best_ask - q.best_bid
            depth = q.bid_size if side.upper() == "SELL" else q.ask_size
            impact = qty / max(depth, 1e-6)
            cost = spread + (q.fee_bps / 1e4) * q.best_ask + 0.01 * impact
            latency_penalty = 0.0001 * q.latency_ms
            score = cost + latency_penalty
            scores.append((score, q.venue))
        scores.sort(key=lambda x: x[0])
        venue = scores[0][1]
        log.info("venue_selected", venue=venue, score=round(scores[0][0], 6))
        return venue

    @staticmethod
    def _select_algo(urgency: str, adv: Optional[float], qty: float) -> str:
        urgency = urgency.lower()
        participation = qty / adv if adv else None
        if urgency == "high":
            return "IS"  # Implementation Shortfall
        if participation and participation > 0.2:
            return "POV"
        if urgency == "medium":
            return "VWAP"
        return "TWAP"

    @staticmethod
    def _slice_order(algo: str, qty: float, horizon_minutes: int = 30, slices: int = 12) -> List[Tuple[float, float]]:
        if algo == "POV":
            return [(qty, 0.0)]
        if slices <= 0:
            return [(qty, 0.0)]
        base = qty / slices
        noise = np.random.uniform(-0.15, 0.15, size=slices)
        schedule = []
        for i, n in enumerate(noise):
            size = max(0.0, base * (1 + n))
            t = (horizon_minutes * 60 / slices) * i
            schedule.append((size, t))
        return schedule
