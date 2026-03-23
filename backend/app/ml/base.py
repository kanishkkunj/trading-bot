"""Base interfaces and utilities for ML models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

import numpy as np
import structlog

log = structlog.get_logger()


@dataclass
class UncertaintyBreakdown:
    """Container for uncertainty diagnostics."""

    entropy: Optional[float] = None
    variance: Optional[float] = None
    ensemble_disagreement: Optional[float] = None
    mc_dropout_std: Optional[float] = None
    conformal_interval: Optional[Tuple[float, float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Rich prediction output used across model types."""

    prediction: Any
    probabilities: Optional[np.ndarray] = None
    confidence: Optional[float] = None
    uncertainty: Optional[UncertaintyBreakdown] = None
    shap_values: Optional[Any] = None
    lime_explanation: Optional[Any] = None
    raw_output: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseProbModel(Protocol):
    """Protocol for probabilistic models used in the stack."""

    def fit(self, X: Any, y: Any, **kwargs: Any) -> None:
        ...

    def predict_proba(self, X: Any, **kwargs: Any) -> np.ndarray:
        ...

    def predict(self, X: Any, **kwargs: Any) -> np.ndarray:
        ...

    def explain(self, X: Any, **kwargs: Any) -> Any:
        ...

    def estimate_uncertainty(self, X: Any, **kwargs: Any) -> UncertaintyBreakdown:
        ...


class ConformalPredictor:
    """Simple conformal predictor for calibrated intervals."""

    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha
        self.residuals: list[float] = []

    def fit(self, y_true: Iterable[float], y_pred: Iterable[float]) -> None:
        residuals = [abs(a - b) for a, b in zip(y_true, y_pred)]
        if not residuals:
            log.warning("conformal_fit_empty", reason="no_residuals")
            return
        self.residuals = residuals

    def predict_interval(self, y_pred: float) -> Tuple[float, float]:
        if not self.residuals:
            return y_pred, y_pred
        q = float(np.quantile(self.residuals, 1 - self.alpha))
        return y_pred - q, y_pred + q


def safe_import(module_name: str, package_hint: str) -> Any:
    """Attempt lazy import and emit a friendly log on failure."""

    try:
        module = __import__(module_name, fromlist=["__dummy__"])
        return module
    except ImportError:  # pragma: no cover - import guard
        log.warning("optional_dependency_missing", module=module_name, install=f"pip install {package_hint}")
        return None


def entropy_from_probs(probs: np.ndarray) -> float:
    """Compute entropy for binary or multi-class probabilities."""

    clipped = np.clip(probs, 1e-8, 1 - 1e-8)
    return float(-np.sum(clipped * np.log(clipped + 1e-12)))


def confidence_from_probs(probs: np.ndarray) -> float:
    """Confidence as max class probability."""

    return float(np.max(probs)) if probs.size else 0.0
