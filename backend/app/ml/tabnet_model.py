"""TabNet model for tabular feature selection with sparse attention."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import structlog

from app.ml.base import BaseProbModel, PredictionResult, UncertaintyBreakdown, confidence_from_probs, entropy_from_probs, safe_import

log = structlog.get_logger()

tabnet_pkg = safe_import("pytorch_tabnet.tab_model", "pytorch-tabnet")


@dataclass
class TabNetConfig:
    input_dim: int
    output_dim: int = 2
    n_d: int = 16
    n_a: int = 16
    n_steps: int = 4
    gamma: float = 1.5
    cat_idxs: Optional[list[int]] = None
    cat_dims: Optional[list[int]] = None
    cat_emb_dim: int = 1
    n_shared: int = 2
    n_independent: int = 2
    momentum: float = 0.02
    lambda_sparse: float = 1e-4


class TabNetModel(BaseProbModel):
    """Wrapper around TabNetClassifier with sparse attention masks."""

    def __init__(self, config: TabNetConfig) -> None:
        if not tabnet_pkg:
            raise ImportError("TabNetModel requires pytorch-tabnet; install with pip install pytorch-tabnet")
        TabNetClassifier = tabnet_pkg.TabNetClassifier  # type: ignore[attr-defined]
        self.config = config
        self.model = TabNetClassifier(
            n_d=config.n_d,
            n_a=config.n_a,
            n_steps=config.n_steps,
            gamma=config.gamma,
            cat_idxs=config.cat_idxs or [],
            cat_dims=config.cat_dims or [],
            cat_emb_dim=config.cat_emb_dim,
            n_shared=config.n_shared,
            n_independent=config.n_independent,
            momentum=config.momentum,
            lambda_sparse=config.lambda_sparse,
        )

    def fit(self, X: np.ndarray, y: np.ndarray, eval_set: Optional[list] = None, max_epochs: int = 50) -> None:
        fit_params = {"max_epochs": max_epochs, "patience": 10, "batch_size": 1024, "virtual_batch_size": 256}
        if eval_set:
            fit_params["eval_set"] = eval_set
        self.model.fit(X_train=X, y_train=y, **fit_params)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        probs = self.predict_proba(X)
        return (probs[:, 1] >= threshold).astype(int)

    def explain(self, X: np.ndarray) -> Any:
        try:
            masks = self.model.explain(X)
            return masks
        except Exception as exc:  # noqa: BLE001
            log.warning("tabnet_explain_failed", error=str(exc))
            return None

    def estimate_uncertainty(self, X: np.ndarray, n_steps: int = 5) -> UncertaintyBreakdown:
        probs = [self.predict_proba(X) for _ in range(n_steps)]
        stacked = np.stack(probs, axis=0)
        mean_probs = stacked.mean(axis=0)
        disagreement = float(stacked.std(axis=0)[:, 1].mean())
        return UncertaintyBreakdown(
            entropy=entropy_from_probs(mean_probs.mean(axis=0)),
            ensemble_disagreement=disagreement,
            metadata={"samples": n_steps},
        )

    def predict_with_filters(
        self, X: np.ndarray, confidence_threshold: float = 0.6, uncertainty_threshold: float = 0.1
    ) -> PredictionResult:
        probs = self.predict_proba(X)
        conf = confidence_from_probs(probs[0]) if len(probs) else None
        uncert = self.estimate_uncertainty(X)
        allowed = (conf or 0) >= confidence_threshold and (uncert.ensemble_disagreement or 0) <= uncertainty_threshold
        return PredictionResult(
            prediction=(probs[:, 1] >= confidence_threshold).astype(int),
            probabilities=probs,
            confidence=conf,
            uncertainty=uncert,
            metadata={"allowed": allowed},
        )
