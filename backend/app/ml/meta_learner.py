"""Stacked ensemble meta-learner with regime-aware weighting and Bayesian fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from sklearn.linear_model import LogisticRegression

from app.ml.base import PredictionResult, UncertaintyBreakdown, confidence_from_probs

log = structlog.get_logger()


@dataclass
class ModelPerformance:
    """Rolling metrics used to adapt weights."""

    accuracy: float
    window_days: int = 30
    last_updated: Optional[str] = None


@dataclass
class MetaLearnerConfig:
    confidence_threshold: float = 0.6
    uncertainty_threshold: float = 0.5
    learning_rate: float = 0.2
    use_bma_fallback: bool = True


class MetaLearner:
    """Combines base learners using stacking + regime-aware weights."""

    def __init__(self, config: MetaLearnerConfig | None = None) -> None:
        self.config = config or MetaLearnerConfig()
        self.base_models: dict[str, Any] = {}
        self.weights: dict[str, float] = {}
        self.performance: dict[str, ModelPerformance] = {}
        self.stack_model = LogisticRegression(max_iter=200)
        self._is_stack_trained = False

    def register_model(self, name: str, model: Any, initial_weight: float = 1.0) -> None:
        self.base_models[name] = model
        self.weights[name] = initial_weight
        self.performance.setdefault(name, ModelPerformance(accuracy=0.5))

    def fit_stacker(self, X_meta: np.ndarray, y: np.ndarray) -> None:
        self.stack_model.fit(X_meta, y)
        self._is_stack_trained = True

    def update_online(self, model_name: str, accuracy: float) -> None:
        perf = self.performance.get(model_name, ModelPerformance(accuracy=0.5))
        lr = self.config.learning_rate
        perf.accuracy = (1 - lr) * perf.accuracy + lr * accuracy
        self.performance[model_name] = perf
        self.weights[model_name] = max(0.01, perf.accuracy)
        self._normalize_weights()

    def _normalize_weights(self) -> None:
        total = sum(self.weights.values()) or 1.0
        for k in self.weights:
            self.weights[k] /= total

    def _bma_weights(self, probs: dict[str, np.ndarray]) -> dict[str, float]:
        # Simplified Bayesian model averaging using entropy as proxy for likelihood
        scores = {}
        for name, p in probs.items():
            entropy = -np.sum(p * np.log(p + 1e-9))
            scores[name] = float(np.exp(-entropy))
        total = sum(scores.values()) or 1.0
        return {k: v / total for k, v in scores.items()}

    def predict(
        self,
        X: Any,
        context: Optional[dict[str, Any]] = None,
    ) -> PredictionResult:
        if not self.base_models:
            raise RuntimeError("No base models registered")
        context = context or {}
        probs: dict[str, np.ndarray] = {}
        uncertainties: dict[str, UncertaintyBreakdown | None] = {}
        for name, model in self.base_models.items():
            proba = model.predict_proba(X)
            probs[name] = proba
            uncertainties[name] = getattr(model, "estimate_uncertainty", lambda *_: None)(X)

        weights = self.weights
        if self.config.use_bma_fallback:
            weights = self._bma_weights({k: v.mean(axis=0) if v.ndim == 3 else v for k, v in probs.items()})
        else:
            self._normalize_weights()
            weights = self.weights

        blended = self._blend(probs, weights)
        confidence = confidence_from_probs(blended[0]) if len(blended) else None
        uncertainty = self._ensemble_uncertainty(uncertainties)
        allowed = (confidence or 0) >= self.config.confidence_threshold and (
            uncertainty.entropy or 0
        ) <= self.config.uncertainty_threshold

        metadata = {
            "weights": weights,
            "regime": context.get("regime"),
            "performance": {k: v.accuracy for k, v in self.performance.items()},
        }

        return PredictionResult(
            prediction=(blended[:, 1] >= self.config.confidence_threshold).astype(int),
            probabilities=blended,
            confidence=confidence,
            uncertainty=uncertainty,
            metadata=metadata,
        )

    def _blend(self, probs: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
        aligned = []
        for name, p in probs.items():
            w = weights.get(name, 0)
            if p.ndim == 3:
                p = p.mean(axis=0)
            aligned.append(w * p)
        return np.sum(aligned, axis=0)

    def _ensemble_uncertainty(self, uncertainties: dict[str, UncertaintyBreakdown | None]) -> UncertaintyBreakdown:
        entropies = [u.entropy for u in uncertainties.values() if u and u.entropy is not None]
        disagreement = [u.ensemble_disagreement for u in uncertainties.values() if u and u.ensemble_disagreement]
        return UncertaintyBreakdown(
            entropy=float(np.mean(entropies)) if entropies else None,
            ensemble_disagreement=float(np.mean(disagreement)) if disagreement else None,
        )
