# Algorithms Used

This file details the algorithms used throughout the Tradecraft application.

## Machine Learning
- **Feature Extraction**: Modules in `engine/features.py` and `engine/features_v2.py` extract features from market data.
- **Model Training**: ML models are trained in `ml/` and `scripts/train_model.py`.
- **Prediction**: Models predict market direction, volatility, and risk.

## Trading Algorithms
- **Order Execution**: Algorithms in `execution/` optimize order placement and minimize slippage.
- **Risk Management**: Algorithms in `risk/` calculate position sizing, stop-loss, and portfolio risk.
- **Options Analytics**: Algorithms in `options_analytics/` calculate Greeks, implied volatility, and pricing.

## Data Ingestion
- **Streaming**: `data_ingestion/stream_handler.py` handles real-time data streams.
- **Sentiment Analysis**: `sentiment/` modules analyze news and social media sentiment.

---
See strategy and engine docs for integration details.