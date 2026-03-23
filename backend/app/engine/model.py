"""ML model wrapper (XGBoost classifier for price direction)."""

from typing import Optional

from sklearn.isotonic import IsotonicRegression

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier, callback


class MLModel:
    """ML model wrapper for trading predictions."""

    def __init__(
        self,
        model_version: str = "v1.0.0",
        random_state: int = 42,
        n_estimators: int = 300,
        max_depth: int = 5,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_weight: float = 1.0,
    ):
        self.model_version = model_version
        self.is_trained = False
        self.feature_names_: list[str] = []
        self.decision_threshold: float = 0.5
        self.calibrator: Optional[IsotonicRegression] = None
        self.model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="logloss",
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            min_child_weight=min_child_weight,
            random_state=random_state,
            tree_method="hist",
        )

    def train(self, X: pd.DataFrame, y: pd.Series, eval_set: Optional[list] = None) -> None:
        """Train the model with optional evaluation set for monitoring (no early stopping)."""
        self.feature_names_ = list(X.columns)
        if eval_set:
            self.model.fit(X, y, eval_set=eval_set, verbose=False)
        else:
            self.model.fit(X, y)
        self.is_trained = True

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Make class predictions (0/1)."""
        self._ensure_trained()
        return self.model.predict(X)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Get prediction probabilities for the positive class."""
        self._ensure_trained()
        raw = self.model.predict_proba(X)
        if self.calibrator is None:
            return raw
        calibrated_pos = self.calibrator.predict(raw[:, 1])
        calibrated_pos = np.clip(calibrated_pos, 0.0, 1.0)
        calibrated_neg = 1.0 - calibrated_pos
        return np.column_stack([calibrated_neg, calibrated_pos])

    def get_feature_importance(self) -> dict[str, float]:
        """Return feature importances keyed by feature name."""
        self._ensure_trained()
        importances = self.model.feature_importances_
        return {name: float(score) for name, score in zip(self.feature_names_, importances)}

    def save(self, path: str) -> None:
        """Persist model to disk."""
        self._ensure_trained()
        joblib.dump(
            {
                "model": self.model,
                "feature_names": self.feature_names_,
                "version": self.model_version,
                "decision_threshold": self.decision_threshold,
                "calibrator": self.calibrator,
            },
            path,
        )

    def load(self, path: str) -> None:
        """Load model from disk."""
        payload = joblib.load(path)
        self.model = payload["model"]
        self.feature_names_ = payload.get("feature_names", [])
        self.model_version = payload.get("version", self.model_version)
        self.decision_threshold = payload.get("decision_threshold", 0.5)
        self.calibrator = payload.get("calibrator")
        self.is_trained = True

    def _ensure_trained(self) -> None:
        if not self.is_trained:
            raise RuntimeError("Model not trained or loaded")
