"""Overfitting prevention utilities."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd


class CPCVSplitter:
    """Combinatorial Purged Cross-Validation splitter."""

    def __init__(self, n_splits: int = 5, embargo: int = 5):
        self.n_splits = n_splits
        self.embargo = embargo

    def split(self, X: pd.DataFrame) -> Iterable[Tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        fold_size = n // self.n_splits
        indices = np.arange(n)
        for i in range(self.n_splits):
            test_idx = indices[i * fold_size : (i + 1) * fold_size]
            embargo_start = max(0, i * fold_size - self.embargo)
            embargo_end = min(n, (i + 1) * fold_size + self.embargo)
            train_idx = np.concatenate([indices[:embargo_start], indices[embargo_end:]])
            yield train_idx, test_idx


def deflated_sharpe_ratio(sharpe: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    if n_obs <= 2:
        return 0.0
    sr = sharpe
    return float(sr * math.sqrt((n_obs - 1) / (n_obs - 2)))


def feature_stability(importances: Sequence[Sequence[float]]) -> float:
    arr = np.array(importances)
    if arr.size == 0:
        return 0.0
    # Stability as mean pairwise Spearman approximation via correlation of ranks
    ranks = np.argsort(np.argsort(-arr, axis=1), axis=1)
    corr = np.corrcoef(ranks)
    if corr.size == 1:
        return 1.0
    upper = corr[np.triu_indices_from(corr, k=1)]
    return float(np.nanmean(upper))
