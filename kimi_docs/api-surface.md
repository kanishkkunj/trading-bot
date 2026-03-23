# API Surface (key endpoints)

Base: `/api/v1`
Auth: Bearer token required for protected routes.

## Auth
- `POST /auth/register` {email, password, full_name} → tokens
- `POST /auth/login` {email, password} → tokens
- `POST /auth/refresh` {refresh_token} → new tokens

## Market
- `GET /market/quote/{symbol}` → live quote
- `GET /market/historical/{symbol}?timeframe&days` → OHLCV
- `GET /market/nifty50` → symbol list

## Orders
- `GET /orders/` (query params: skip, limit, symbol, status)
- `GET /orders/{id}`
- `POST /orders/` {symbol, side, order_type, quantity, price?}
- `POST /orders/{id}/cancel`

## Portfolio
- `GET /portfolio/positions` → open positions
- `GET /portfolio/summary` → totals (market value, cost, PnL)
- `GET /portfolio/pnl` → cash, equity, exposures, daily/total PnL and pct

## Paper Trading
- `POST /paper/run?top_k=5` → runs ML + rules, places orders; returns executed list `{executed, count}`

## Backtest
- `POST /backtest/run` {symbol, start_date, end_date, initial_capital?, position_size_pct?}
- `GET /backtest/quick/{symbol}?days=365`

## Risk
- `GET /risk/status`
- `GET /risk/limits`
- `POST /risk/kill-switch?active=bool`

## Admin (stub)
- `GET /admin/health` (if present)
