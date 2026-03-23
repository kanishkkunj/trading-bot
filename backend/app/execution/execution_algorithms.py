"""Execution algorithms: TWAP, VWAP, Iceberg, Adaptive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

import numpy as np


@dataclass
class ExecutionSlice:
    qty: float
    target_time_sec: float


@dataclass
class ExecutionPlan:
    slices: List[ExecutionSlice]
    algo: str
    notes: str | None = None


def twap_plan(total_qty: float, horizon_sec: int = 1800, slices: int = 12) -> ExecutionPlan:
    base = total_qty / max(slices, 1)
    noise = np.random.uniform(-0.2, 0.2, size=max(slices, 1))
    plan = [ExecutionSlice(qty=max(0.0, base * (1 + n)), target_time_sec=i * horizon_sec / max(slices, 1)) for i, n in enumerate(noise)]
    return ExecutionPlan(slices=plan, algo="TWAP", notes="randomized")


def vwap_plan(total_qty: float, hist_profile: List[float]) -> ExecutionPlan:
    if not hist_profile:
        return twap_plan(total_qty)
    weights = np.array(hist_profile) / max(1e-6, sum(hist_profile))
    plan = [ExecutionSlice(qty=float(total_qty * w), target_time_sec=float(i * (3600 / len(weights)))) for i, w in enumerate(weights)]
    return ExecutionPlan(slices=plan, algo="VWAP", notes="hist_profile")


def iceberg_plan(total_qty: float, clip_size: float, refresh_time: float = 60.0) -> ExecutionPlan:
    clips = int(np.ceil(total_qty / max(clip_size, 1e-6)))
    plan = [ExecutionSlice(qty=float(min(clip_size, total_qty - i * clip_size)), target_time_sec=float(i * refresh_time)) for i in range(clips)]
    return ExecutionPlan(slices=plan, algo="ICEBERG", notes="hidden_size")


def adaptive_plan(total_qty: float, price_path: List[float], favorable_fn: Callable[[float], bool]) -> ExecutionPlan:
    if not price_path:
        return twap_plan(total_qty)
    slices: list[ExecutionSlice] = []
    step = len(price_path)
    for i, px in enumerate(price_path):
        weight = 1.5 if favorable_fn(px) else 0.5
        qty = (total_qty / step) * weight
        slices.append(ExecutionSlice(qty=qty, target_time_sec=i * 60))
    return ExecutionPlan(slices=slices, algo="ADAPTIVE", notes="price_sensitive")
