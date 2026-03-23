# Workflows

## Run full stack (dev)
1) `docker-compose up postgres redis backend` (from repo root)
2) Frontend: `cd frontend && npm run dev -- --port 3002`
3) Open http://localhost:3002 ; backend at http://localhost:8000

## Authenticate
- Register (`/auth/register`) or login via UI. Tokens stored in localStorage. Ensure `NEXT_PUBLIC_API_URL` matches backend.

## Run paper trader (live)
1) Log in on frontend.
2) From Orders or Signals page, click "Run Paper Trader" (defaults top_k=5).
3) Backend uses live quotes, filters illiquid/wide spreads, applies model + Cognee recall bias, enforces capital/buying-power, executes via paper broker.
4) Dashboard/Portfolio auto-refresh via React Query invalidations.

## Inspect performance
- Dashboard stats: cash, equity, total/daily P&L, P&L %, open positions.
- Portfolio page: equity, cash, total P&L, P&L %, positions table with unrealized P&L.
- Orders page: list of executed/placed/rejected orders.

## Reset paper account
- Backend: `docker exec tradecraft-backend python scripts/reset_paper.py <user_id>` to wipe orders/positions/signals for that user.

## Backtest
- Use UI Backtest page (if wired) or call `POST /api/v1/backtest/run` with symbol/date range; quick backtest via `GET /backtest/quick/{symbol}?days=365`. Results can be logged to Cognee (summary/trades).

## Troubleshooting
- Frontend port busy: use `npm run dev -- --port 3002`.
- CORS/auth errors: ensure logged in; check `NEXT_PUBLIC_API_URL`; verify backend on 8000.
- Paper trade skipped: symbol may fail quality filters (bid/ask zero, spread >1%, volume <10k) or hit per-trade cap/buying power.
- Model missing: ensure `app/engine/artifacts/xgb_nifty50_ensemble.bin` exists in backend container.
