"""Event-driven backtester with slippage, impact, latency, and parallel sweeps."""

from __future__ import annotations

import math
import multiprocessing as mp
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    pnl: float
    equity_curve: pd.Series
    trades: List[dict]
    stats: Dict[str, float]


class EventBacktester:
    """Tick-level event backtester with microstructure controls."""

    def __init__(
        self,
        slippage_bps: float = 1.0,
        impact_coeff: float = 0.1,
        latency_ms: int = 50,
    ) -> None:
        self.slippage_bps = slippage_bps
        self.impact_coeff = impact_coeff
        self.latency_ms = latency_ms

    def _apply_slippage(self, price: float, side: str) -> float:
        adj = price * (self.slippage_bps / 10_000)
        return price + adj if side == "buy" else price - adj

    def _apply_impact(self, price: float, quantity: float, avg_vol: float) -> float:
        if avg_vol <= 0:
            return price
        impact = self.impact_coeff * (quantity / avg_vol)
        return price * (1 + impact)

    def _simulate_latency(self, ts: pd.Timestamp, df: pd.DataFrame) -> pd.Timestamp:
        return ts + pd.Timedelta(milliseconds=self.latency_ms)

    def run(
        self,
        ticks: pd.DataFrame,
        signals: Iterable[Tuple[pd.Timestamp, str, str, int]],
        avg_volume: float,
    ) -> BacktestResult:
        equity = 0.0
        trades: List[dict] = []
        cash = 0.0
        position: Dict[str, int] = {}
        equity_curve = []

        price_map = ticks.set_index("ts")["price"]

        for ts, symbol, side, qty in signals:
            delayed_ts = self._simulate_latency(ts, ticks)
            if delayed_ts not in price_map:
                continue
            px = float(price_map.loc[delayed_ts])
            px = self._apply_slippage(px, side)
            px = self._apply_impact(px, qty, avg_volume)

            direction = 1 if side == "buy" else -1
            cash -= px * qty * direction
            position[symbol] = position.get(symbol, 0) + qty * direction
            trades.append({"ts": delayed_ts, "symbol": symbol, "side": side, "qty": qty, "price": px})

            m2m = sum(position.get(sym, 0) * price_map.get(delayed_ts, px) for sym in position)
            equity = cash + m2m
            equity_curve.append((delayed_ts, equity))

        curve = pd.Series({ts: eq for ts, eq in equity_curve}).sort_index()
        pnl = curve.iloc[-1] if not curve.empty else 0.0
        stats = self._stats(curve)
        return BacktestResult(pnl=pnl, equity_curve=curve, trades=trades, stats=stats)

    def _stats(self, curve: pd.Series) -> Dict[str, float]:
        if curve.empty:
            return {"pnl": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
        returns = curve.diff().fillna(0)
        sharpe = returns.mean() / (returns.std() + 1e-9) * math.sqrt(252 * 6.5 * 60)
        roll_max = curve.cummax()
        dd = ((curve - roll_max) / (roll_max + 1e-9)).min()
        return {
            "pnl": float(curve.iloc[-1]),
            "sharpe": float(sharpe),
            "max_drawdown": float(dd),
        }

    def parameter_sweep(
        self,
        ticks: pd.DataFrame,
        signals: Iterable[Tuple[pd.Timestamp, str, str, int]],
        avg_volume: float,
        sweep: List[Dict[str, float]],
        workers: int = 4,
    ) -> List[Tuple[Dict[str, float], BacktestResult]]:
        payloads = []
        for params in sweep:
            payloads.append((params, ticks, signals, avg_volume))

        with mp.Pool(processes=workers) as pool:
            results = pool.starmap(_run_wrapper, [(self, p) for p in payloads])
        return results


def _run_wrapper(bt_and_payload: Tuple[EventBacktester, Tuple[Dict[str, float], pd.DataFrame, Iterable, float]]):
    bt, (params, ticks, signals, avg_volume) = bt_and_payload
    bt = EventBacktester(
        slippage_bps=params.get("slippage_bps", bt.slippage_bps),
        impact_coeff=params.get("impact_coeff", bt.impact_coeff),
        latency_ms=params.get("latency_ms", bt.latency_ms),
    )
    res = bt.run(ticks=ticks, signals=signals, avg_volume=avg_volume)
    return params, res
