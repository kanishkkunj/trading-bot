# Machine Learning Models

This file explains the ML models used in the application.

## Location
- ML logic is in `backend/app/ml/` and `engine/model.py`.
- Training scripts are in `scripts/train_model.py`.

## Types of Models
- **Classification**: Predicts market direction (up/down).
- **Regression**: Predicts price, volatility, or risk.
- **Feature Extraction**: `features.py` and `features_v2.py` extract features for models.

## Training & Usage
- Models are trained on historical data using scripts.
- Predictions are used by strategies and risk modules.

## Extending ML
- Add new models to `ml/` and update training scripts.

---
See algorithms and data flow docs for details.