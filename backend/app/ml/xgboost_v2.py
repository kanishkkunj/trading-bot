"""Improved XGBoost model with calibration and interpretability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import structlog
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from xgboost import XGBClassifier

from app.ml.base import (
    BaseProbModel,
    ConformalPredictor,
    PredictionResult,
    UncertaintyBreakdown,
    confidence_from_probs,
    entropy_from_probs,
    safe_import,
)

log = structlog.get_logger()


@dataclass
class CalibrationConfig:
    """Calibration settings for probabilistic outputs."""

    method: str = "platt"  # platt or isotonic or none
    enabled: bool = True


class XGBoostV2(BaseProbModel):
    """XGBoost wrapper with calibration, SHAP, and uncertainty estimates."""

    def __init__(
        self,
        model_version: str = "xgb-v2",
        calibration: CalibrationConfig | None = None,
        **xgb_params: Any,
    ) -> None:
        default_params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "n_estimators": 400,
            "max_depth": 5,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_weight": 1.0,
            "random_state": 42,
            "tree_method": "hist",
        }
        merged = {**default_params, **xgb_params}
        self.model = XGBClassifier(**merged)
        self.model_version = model_version
        self.calibration = calibration or CalibrationConfig()
        self.calibrator: LogisticRegression | IsotonicRegression | None = None
        self.conformal = ConformalPredictor()
        self._shap = safe_import("shap", "shap")
        self.feature_names: list[str] = []

    def fit(
        self,
        X: Any,
        y: Any,
        calibration_data: Optional[Tuple[Any, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self.feature_names = list(getattr(X, "columns", [])) or []
        self.model.fit(X, y, **kwargs)
        if self.calibration.enabled and calibration_data:
            self._fit_calibrator(calibration_data[0], calibration_data[1])
        if calibration_data:
            self.conformal.fit(calibration_data[1], self.predict_proba(calibration_data[0])[:, 1])

    def _fit_calibrator(self, X_cal: Any, y_cal: Any) -> None:
        raw = self.model.predict_proba(X_cal)[:, 1]
        method = (self.calibration.method or "platt").lower()
        if method == "isotonic":
            self.calibrator = IsotonicRegression(out_of_bounds="clip")
        else:
            self.calibrator = LogisticRegression(max_iter=1000)
        self.calibrator.fit(raw.reshape(-1, 1) if raw.ndim == 1 else raw.reshape(-1, 1), y_cal)

    def _apply_calibration(self, raw_probs: np.ndarray) -> np.ndarray:
        if self.calibrator is None:
            return raw_probs
        calibrated_pos = self.calibrator.predict(raw_probs[:, 1].reshape(-1, 1))
        calibrated_pos = np.clip(calibrated_pos, 0.0, 1.0)
        calibrated_neg = 1.0 - calibrated_pos
        return np.column_stack([calibrated_neg, calibrated_pos])

    def predict_proba(self, X: Any, **_: Any) -> np.ndarray:
        raw = self.model.predict_proba(X)
        return self._apply_calibration(raw)

    def predict(self, X: Any, threshold: float = 0.5, **kwargs: Any) -> np.ndarray:
        probs = self.predict_proba(X, **kwargs)[:, 1]
        return (probs >= threshold).astype(int)

    def explain(self, X: Any, sample_size: int = 256, **_: Any) -> Any:
        if self._shap is None:
            return None
        try:
            background = X[:sample_size] if len(X) > sample_size else X
            explainer = self._shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(X, check_additivity=False)
            expected_value = explainer.expected_value
            return {"shap_values": shap_values, "expected_value": expected_value, "background": background}
        except Exception as exc:  # noqa: BLE001
            log.warning("shap_failed", error=str(exc))
            return None

    def estimate_uncertainty(self, X: Any, mc_runs: int = 0, **kwargs: Any) -> UncertaintyBreakdown:
        probs = self.predict_proba(X, **kwargs)
        entropy = entropy_from_probs(probs.mean(axis=0)) if probs.ndim == 2 else None
        return UncertaintyBreakdown(entropy=entropy, metadata={"mc_runs": mc_runs})

    def predict_with_risk_controls(
        self, X: Any, confidence_threshold: float = 0.6, uncertainty_threshold: float = 0.5
    ) -> PredictionResult:
        probs = self.predict_proba(X)
        preds = (probs[:, 1] >= confidence_threshold).astype(int)
        conf = confidence_from_probs(probs[0]) if len(probs) else None
        uncert = self.estimate_uncertainty(X)
        allowed = (conf or 0) >= confidence_threshold and (uncert.entropy or 0) <= uncertainty_threshold
        interval = self.conformal.predict_interval(float(probs[0, 1])) if len(probs) else None
        if uncert:
            uncert.conformal_interval = interval
        return PredictionResult(
            prediction=preds,
            probabilities=probs,
            confidence=conf,
            uncertainty=uncert,
            shap_values=None,
            metadata={"model_version": self.model_version, "allowed": allowed},
        )

    def feature_importances(self) -> Dict[str, float]:
        scores = getattr(self.model, "feature_importances_", [])
        return {name: float(score) for name, score in zip(self.feature_names, scores)}
