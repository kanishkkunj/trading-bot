"""Real-time stream handler for live ticks and microstructure features."""

from __future__ import annotations

import asyncio
import collections
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple

try:  # Optional metrics
    from prometheus_client import Counter, Summary
except Exception:  # noqa: BLE001
    Counter = Summary = None  # type: ignore

try:
    import websockets
except Exception:  # noqa: BLE001
    websockets = None  # type: ignore


@dataclass
class Level:
    price: float
    size: float


@dataclass
class OrderBook:
    bids: List[Level]
    asks: List[Level]
    ts: float


class StreamHandler:
    """Manage WebSocket connections, reconstruct order books, compute microstructure."""

    def __init__(self, url: str, symbols: List[str]):
        self.url = url
        self.symbols = symbols
        self._ws = None
        self._latency = Summary("stream_tick_latency_seconds", "Latency of tick handling") if Summary else None
        self._ticks = Counter("stream_ticks_total", "Total ticks processed") if Counter else None
        self.book: Dict[str, OrderBook] = {}
        self.trades: Deque[Tuple[str, float, float, float]] = collections.deque(maxlen=5000)

    async def connect(self):
        if websockets is None:
            raise RuntimeError("websockets not installed")
        self._ws = await websockets.connect(self.url)
        await self._subscribe(self.symbols)

    async def _subscribe(self, symbols: List[str]):
        if self._ws:
            await self._ws.send({"type": "subscribe", "symbols": symbols}.__str__())

    async def run(self, handler):
        if not self._ws:
            await self.connect()
        async for raw in self._ws:  # type: ignore
            if self._latency:
                with self._latency.time():
                    await self._handle_message(raw, handler)
            else:
                await self._handle_message(raw, handler)

    async def _handle_message(self, raw: Any, handler):
        if self._ticks:
            self._ticks.inc()
        msg = self._parse(raw)
        if not msg:
            return
        if msg.get("type") == "l2":
            self._update_order_book(msg)
        if msg.get("type") == "trade":
            self._handle_trade(msg)
        await handler(msg)

    def _parse(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, str):
            # Assuming server sends JSON string; do not import json to keep light
            try:
                import json

                return json.loads(raw)
            except Exception:  # noqa: BLE001
                return {}
        if isinstance(raw, dict):
            return raw
        return {}

    def _update_order_book(self, msg: Dict[str, Any]):
        symbol = msg.get("symbol")
        bids = [Level(price=float(b[0]), size=float(b[1])) for b in msg.get("bids", [])]
        asks = [Level(price=float(a[0]), size=float(a[1])) for a in msg.get("asks", [])]
        ts = float(msg.get("ts", 0.0))
        self.book[symbol] = OrderBook(bids=bids, asks=asks, ts=ts)

    def _handle_trade(self, msg: Dict[str, Any]):
        symbol = msg.get("symbol")
        price = float(msg.get("price", 0.0))
        size = float(msg.get("size", 0.0))
        ts = float(msg.get("ts", 0.0))
        # Aggressor side detection using mid
        book = self.book.get(symbol)
        side = "unknown"
        if book and book.bids and book.asks:
            mid = (book.bids[0].price + book.asks[0].price) / 2
            side = "buy" if price > mid else "sell" if price < mid else "mid"
        self.trades.append((symbol, price, size, ts))
        msg["aggressor"] = side

    def order_flow_imbalance(self, symbol: str, depth: int = 5) -> float:
        book = self.book.get(symbol)
        if not book:
            return 0.0
        buy = sum(l.size for l in book.bids[:depth])
        sell = sum(l.size for l in book.asks[:depth])
        denom = buy + sell or 1.0
        return (buy - sell) / denom

    def vpin(self, symbol: str, window: int = 50) -> float:
        trades = [t for t in list(self.trades)[-window:] if t[0] == symbol]
        if not trades:
            return 0.0
        buy_vol = sum(t[2] for t in trades if t[1] >= (self.book.get(symbol).asks[0].price if self.book.get(symbol) and self.book[symbol].asks else 0))
        sell_vol = sum(t[2] for t in trades if t[1] <= (self.book.get(symbol).bids[0].price if self.book.get(symbol) and self.book[symbol].bids else 0))
        total = buy_vol + sell_vol or 1.0
        return abs(buy_vol - sell_vol) / total
