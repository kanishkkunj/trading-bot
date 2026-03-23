# Architecture

## Overview
- **Backend**: FastAPI app (`backend/app`) providing auth, market data, orders, portfolio, paper trading, backtests, risk. Uses Postgres (Timescale) and Redis. Runs via uvicorn.
- **Frontend**: Next.js 14 app (`frontend/src`) with app router, Tailwind UI, React Query data layer, axios client configured with `NEXT_PUBLIC_API_URL`.
- **Data**: Market data from Yahoo Finance (and Zerodha client if configured). Features built via `FeatureEngine`. Model artifact at `app/engine/artifacts/xgb_nifty50_ensemble.bin`.
- **Paper Trading**: `PaperTradeService` orchestrates ML inference, applies quality filters and Cognee recall bias, creates signals/orders, executes via `PaperBroker` using live quotes.
- **Persistence**: SQLAlchemy models in `backend/app/models`, Pydantic schemas in `backend/app/schemas`. Alembic migrations scaffold under `backend/alembic.ini` (migrations folder placeholder).
- **Memory (Cognee)**: `MemoryService` logs signals/orders/backtests; `CogneeClient` handles HTTP to Cognee API.
- **Infra**: Docker Compose defines postgres, redis, backend (reload), frontend. `.env` holds API keys and DB URLs.

## Data Flow (paper trading)
1. Frontend calls `POST /api/v1/paper/run`.
2. Backend validates auth, invokes `PaperTradeService.run`.
3. Fetch features/history (yfinance), compute proba via ensemble model; fetch live quote; apply bid/ask spread & volume filters; apply Cognee recall bias to confidence.
4. Create `Signal` records; create `Order` via `OrderService` with capital/buying-power checks; execute through `PaperBroker` (fills with slippage/rejections simulation).
5. Portfolio updated via `PortfolioService.update_position_from_order`; account snapshot recalculates cash/equity. Responses return executed orders list.
6. Frontend invalidates queries (`orders`, `positions`, `portfolio-summary`, `pnl`) to refresh dashboard/portfolio.

## Auth Flow
- JWT access/refresh with secret, HS256. `auth.py` routes for login/register/refresh. Dependencies in `deps.py` enforce current active user.

## Frontend Data Flow
- `src/lib/api.ts`: axios client adds bearer from localStorage; refreshes token on 401.
- `use-*` hooks fetch via React Query; pages/components render data. Stats/portfolio show cash/equity/PnL.

## Reset Flow
- `backend/scripts/reset_paper.py` clears user orders/positions/signals for a clean paper account.

## Configuration
- Environment variables: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, token expiry, `PAPER_INITIAL_CAPITAL`, Cognee keys, Zerodha keys, `NEXT_PUBLIC_API_URL` for frontend.
