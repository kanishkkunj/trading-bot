# Data & ML

## Feature Engineering
- `app/engine/features.py`: builds engineered features from OHLCV (technical indicators, rolling stats). Used by paper trader and backtests.
- Input data from yfinance (`MarketService._fetch_from_yfinance`) stored to DB for reuse.

## Models
- Artifact: `app/engine/artifacts/xgb_nifty50_ensemble.bin` containing `long` and `short` models, weights, decision threshold.
- `PaperTradeService` loads artifact per run: computes proba_long/proba_short, combines via weights to a single probability.

## Paper Trade Logic (ML + Rules)
- History fetch: yfinance 400d daily; feature columns aligned to model; latest row scaled using recent means/stds.
- Confidence threshold: min_conf = max(model threshold, 0.55) to avoid low-quality trades.
- Quality filters (live quote): require bid/ask >0, spread <=1%, volume >=10k; skip if missing.
- Live pricing: uses `get_live_quote`; falls back to latest close only if live price missing after quality filters.
- Position sizing: 5% of `PAPER_INITIAL_CAPITAL`, capped to 200 shares; returns 0 if price too high or invalid.
- Capital controls: `OrderService` enforces per-trade notional cap (5% of initial capital) and buying power checks.
- Cognee recall bias: pulls recent signal memories per symbol; adjusts confidence by up to ±6% before ranking top_k.
- Logging to Cognee: each signal’s features/decision logged via `MemoryService.log_signal_context` (fail-soft if disabled).

## Backtesting
- `backtest` routes call into `backtest_service` (not fully detailed here) to simulate strategies over historical data and can log summaries to Cognee (`MemoryService.log_backtest_summary`).

## Risk / Policy
- `OrderService` and `PortfolioService` handle PnL, cash/equity. `risk` module currently stubbed; kill-switch endpoint exists but logic minimal.
