"""Sentiment aggregation, momentum/divergence, and trading hooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.sentiment.nlp_processor import SentimentResult, EventExtraction


@dataclass
class SentimentRecord:
    as_of: datetime
    symbol: str
    sector: Optional[str]
    score: float
    label: str
    source: str
    event_tags: List[str]
    price: Optional[float] = None


@dataclass
class Alert:
    as_of: datetime
    symbol: str
    message: str
    severity: str = "info"


class SentimentAnalytics:
    """Aggregates sentiment streams and produces trading-relevant views."""

    def __init__(self, momentum_window: int = 5, divergence_window: int = 5) -> None:
        self.momentum_window = momentum_window
        self.divergence_window = divergence_window

    def aggregate_by_symbol(self, records: List[SentimentRecord]) -> Dict[str, float]:
        agg: Dict[str, List[float]] = {}
        for r in records:
            agg.setdefault(r.symbol, []).append(r.score)
        return {k: float(np.mean(v)) for k, v in agg.items()}

    def aggregate_by_sector(self, records: List[SentimentRecord]) -> Dict[str, float]:
        agg: Dict[str, List[float]] = {}
        for r in records:
            if r.sector is None:
                continue
            agg.setdefault(r.sector, []).append(r.score)
        return {k: float(np.mean(v)) for k, v in agg.items()}

    def momentum(self, scores: List[float]) -> float:
        arr = np.asarray(scores[-self.momentum_window :], dtype=float)
        if arr.size < 2:
            return 0.0
        return float(arr[-1] - arr[0])

    def divergence(self, prices: List[float], scores: List[float]) -> float:
        if not prices or not scores:
            return 0.0
        p = np.asarray(prices[-self.divergence_window :], dtype=float)
        s = np.asarray(scores[-self.divergence_window :], dtype=float)
        if p.size < 2 or s.size < 2:
            return 0.0
        return float((p[-1] - p[0]) - (s[-1] - s[0]))

    def event_impact(self, history: List[Tuple[str, float]]) -> Dict[str, float]:
        """Estimate impact by event tag based on average score."""
        impact: Dict[str, List[float]] = {}
        for tag, score in history:
            impact.setdefault(tag, []).append(score)
        return {k: float(np.mean(v)) for k, v in impact.items()}

    def trading_filters(
        self,
        records: List[SentimentRecord],
        upcoming_events: Dict[str, datetime],
        pcr_spike: bool = False,
    ) -> Dict[str, bool]:
        """Decide if trades are allowed: block before earnings or sentiment conflicts."""
        decisions: Dict[str, bool] = {}
        avg = self.aggregate_by_symbol(records)
        now = datetime.utcnow()
        for sym, score in avg.items():
            block = False
            event_time = upcoming_events.get(sym)
            if event_time and 0 <= (event_time - now).total_seconds() <= 36 * 3600:
                block = True
            if pcr_spike and score > 0:
                block = True
            decisions[sym] = not block
        return decisions

    def sentiment_confirmation(self, records: List[SentimentRecord], threshold: float = 0.1) -> Dict[str, str]:
        avg = self.aggregate_by_symbol(records)
        confirm: Dict[str, str] = {}
        for sym, score in avg.items():
            if score >= threshold:
                confirm[sym] = "long_ok"
            elif score <= -threshold:
                confirm[sym] = "short_ok"
            else:
                confirm[sym] = "neutral"
        return confirm

    def alert_spikes(self, records: List[SentimentRecord], z: float = 2.5) -> List[Alert]:
        alerts: List[Alert] = []
        by_sym: Dict[str, List[SentimentRecord]] = {}
        for r in records:
            by_sym.setdefault(r.symbol, []).append(r)
        for sym, recs in by_sym.items():
            scores = np.asarray([r.score for r in recs], dtype=float)
            if scores.size < 3:
                continue
            mean = scores.mean()
            std = scores.std() + 1e-6
            if abs(scores[-1] - mean) > z * std:
                alerts.append(Alert(as_of=recs[-1].as_of, symbol=sym, message="sentiment spike", severity="warning"))
        return alerts

    def breaking_news_impact(self, rec: SentimentRecord, events: EventExtraction) -> Alert:
        sev = "info"
        if rec.score <= -0.3 or ("regulatory" in events.events):
            sev = "critical"
        return Alert(as_of=rec.as_of, symbol=rec.symbol, message="breaking news", severity=sev)

    def store_timeseries_payload(self, records: List[SentimentRecord]) -> List[dict]:
        """Prepare rows for insertion into a TimescaleDB hypertable (caller writes)."""
        rows = []
        for r in records:
            rows.append(
                {
                    "as_of": r.as_of,
                    "symbol": r.symbol,
                    "sector": r.sector,
                    "score": r.score,
                    "label": r.label,
                    "source": r.source,
                    "event_tags": r.event_tags,
                    "price": r.price,
                }
            )
        return rows

    def expiry_bias(self, as_of: datetime, expiry: datetime, window_days: int = 2) -> float:
        days = (expiry - as_of).days
        return float(max(0.0, window_days - abs(days)) / window_days)

    def sentiment_momentum_flag(self, records: List[SentimentRecord]) -> Dict[str, float]:
        by_sym: Dict[str, List[float]] = {}
        for r in records:
            by_sym.setdefault(r.symbol, []).append(r.score)
        return {k: self.momentum(v) for k, v in by_sym.items()}

    def divergence_flag(self, prices: Dict[str, List[float]], scores: Dict[str, List[float]]) -> Dict[str, float]:
        flags: Dict[str, float] = {}
        for sym, p in prices.items():
            flags[sym] = self.divergence(p, scores.get(sym, []))
        return flags

    def event_driven_signal(self, rec: SentimentRecord, events: EventExtraction) -> str:
        if "earnings" in events.events and rec.score > 0:
            return "post_earnings_drift_long"
        if "regulatory" in events.events and rec.score < 0:
            return "regulatory_short"
        return "none"
