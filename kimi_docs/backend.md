# Backend (FastAPI)

## Entry & Config
- `app/main.py`: creates FastAPI app, CORS (localhost ports), includes routers for auth/admin/market/orders/portfolio/signals/strategy/backtest/risk/paper. Startup/shutdown logs.
- `app/config.py`: pydantic settings for DB, Redis, JWT, env, Cognee, Zerodha, paper initial capital.
- `app/deps.py`: DB session dependency, current active user dependency.

## Routers (`app/api`)
- `auth.py`: register/login/refresh; returns JWTs.
- `admin.py`: admin endpoints (stub/minimal).
- `market.py`: quotes, historical, NIFTY50 list.
- `orders.py`: CRUD/cancel for orders; uses `OrderService`.
- `portfolio.py`: positions, summary, pnl; uses `PortfolioService`.
- `signals.py`: list/create signals.
- `strategy.py`: strategy management (minimal stub).
- `backtest.py`: run/quick backtest; logs via MemoryService.
- `risk.py`: risk status/limits/kill-switch (stub logic).
- `paper.py`: `POST /paper/run` triggers PaperTradeService; returns executed orders.

## Services
- `market_service.py`: live quotes (Zerodha if enabled else yfinance), historical fetch/store, NIFTY50 symbols.
- `order_service.py`: capital checks (5% per-trade cap, cash/buying-power, short constraints), fetch live quote if price missing, create/cancel/update orders, execute via `PaperBroker`, update portfolio.
- `portfolio_service.py`: positions retrieval, account snapshot (cash/equity/long_cost/short_proceeds/open_value), PnL calc (realized/unrealized), daily PnL, price refresh, position updates from orders.
- `paper_trade_service.py`: runs ensemble model, builds features, applies live-price quality filters (bid/ask >0, spread <=1%, volume >=10k), applies higher confidence threshold, Cognee recall bias, creates signals, places orders; logs signal context to Cognee when enabled.
- `signal_service.py`: CRUD for signals.
- `memory_service.py`: wrappers to log orders, backtests, signals to Cognee.
- `backtest_service.py`: quick/backtest logic (uses features/models, omitted details here but routes call into it).
- `risk_service.py`: stub for risk limits/kill switch.
- `paper_trade_service` uses `FeatureEngine` (`app/engine/features.py`) for feature computation.

## Brokers
- `broker/paper.py`: simulates fills with small slippage, rejection rate, partial fill rate. Uses live quote; sets order status/avg price/timestamps.
- `broker/base.py`: interface base class. `broker/zerodha.py` placeholder for real broker.

## Clients
- `clients/zerodha_client.py`: Zerodha API wrapper (enabled flag based on keys). Used by MarketService.
- `clients/cognee_client.py`: HTTP client to Cognee memory API; upsert/search with bearer auth.

## Engine
- `engine/features.py`: computes engineered features from OHLCV (technical indicators). Used by model and paper trader.
- `engine/model.py`, `policy.py`, `risk.py`, `rules.py`, `scheduler.py`: scaffolding for model/policy/risk/rules/scheduler (light logic or placeholders).
- `engine/artifacts/xgb_nifty50_ensemble.bin`: serialized ensemble models (long/short) + weights/threshold.

## Models (`app/models`)
- SQLAlchemy ORM models: `user`, `order`, `position`, `signal`, `candle`, `strategy`, `audit`.
- `position.py`: market_value/cost_basis use abs qty; realized/unrealized PnL fields.

## Schemas (`app/schemas`)
- Pydantic request/response for auth, market, order, portfolio, signal, etc. `portfolio.py` exposes PnL with cash/equity/exposures.

## Alerts/Notifications
- `alerts/email.py`, `telegram.py`, `whatsapp.py`: stubs/utilities for alert channels.

## DB & Migrations
- `db/session.py`: async session creation (SQLAlchemy + asyncpg). `db/migrations/` placeholder for Alembic migrations. `alembic.ini` configured.

## Scripts
- `backend/scripts/train_model.py`: model training entry.
- `backend/scripts/reset_paper.py`: wipe paper orders/positions/signals for a user (clean slate).

## Tests
- `backend/tests/*`: pytest suites for auth, features, orders, paper broker, risk, strategy; memory service fake Cognee client.

## Error Handling
- `paper.py` converts domain `ValueError` to HTTP 400. Services raise ValueError for validation (caps/buying power/missing price). CORS allows localhost dev ports.
