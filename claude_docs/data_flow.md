# Data Flow & Ingestion

This file explains how data moves through the Tradecraft application.

## Data Sources
- **Market Data**: Fetched from NSE, Yahoo Finance via `data/provider_nse.py` and `data/provider_yfinance.py`.
- **Options Data**: Managed in `data_ingestion/options_data.py`.
- **Institutional Flow**: Managed in `data_ingestion/institutional_flow.py`.
- **Sentiment Feed**: Managed in `data_ingestion/sentiment_feed.py`.

## Data Pipeline
1. **Fetch**: Data is fetched from external APIs.
2. **Ingest**: Data is processed and stored via `data_ingestion/` modules.
3. **Feature Extraction**: `engine/features.py` extracts features for ML and strategies.
4. **Usage**: Data is used by strategies, risk, and execution modules.

## Real-Time Streaming
- `stream_handler.py` manages real-time data streams for live trading.

---
See ML and strategy docs for how data is used.