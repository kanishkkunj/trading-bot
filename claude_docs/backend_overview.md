# Backend Overview

The backend is a Python application built with FastAPI. It handles trading logic, data ingestion, machine learning, and API endpoints.

## Key Modules
- **alerts/**: Sends notifications via email, telegram, whatsapp.
- **api/**: Exposes REST endpoints for admin, authentication, backtesting, market data, orders, paper trading, portfolio, risk, signals, strategy, and websocket communication.
- **broker/**: Integrates with brokers (Zerodha, paper trading).
- **clients/**: Client wrappers for external APIs (Cognee, Zerodha).
- **data/**: Fetches and provides market data from NSE and Yahoo Finance.
- **data_ingestion/**: Manages institutional flow, market data, options, sentiment feeds, and streaming.
- **db/**: Database session management and migrations.
- **engine/**: Core trading engine, feature extraction, model management, policy enforcement.
- **execution/**: Trade execution logic.
- **institutional/**: Institutional trading logic.
- **ml/**: Machine learning models and utilities.
- **models/**: Data models and schemas.
- **monitoring/**: System and trading monitoring.
- **options_analytics/**: Options analytics and calculations.
- **research/**: Research utilities.
- **risk/**: Risk management logic.
- **schemas/**: Pydantic schemas for data validation.
- **scripts/**: Backend scripts for maintenance and training.
- **sentiment/**: Sentiment analysis modules.
- **services/**: Service layer abstractions.
- **strategy/**: Trading strategies.
- **tests/**: Unit and integration tests.

---
See module-specific files for detailed explanations.