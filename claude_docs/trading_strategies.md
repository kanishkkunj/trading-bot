# Trading Strategies

This file explains the trading strategies implemented in the Tradecraft backend.

## Location
- Strategies are mainly found in `backend/app/strategy/`.

## Types of Strategies
- **Momentum**: Buys assets showing upward price movement.
- **Mean Reversion**: Buys assets that have fallen below their average price, expecting a rebound.
- **Options Strategies**: Includes spreads, straddles, and other options-based approaches.
- **Institutional Flow**: Uses institutional order flow data to inform trades.
- **ML-Based**: Uses machine learning models to predict market direction and optimize trades.

## How Strategies Work
- Each strategy module defines entry/exit rules, risk management, and position sizing.
- Strategies interact with the broker and data modules to place orders and fetch market data.
- Backtesting is supported via the `api/backtest.py` endpoint.

## Customization
- Strategies can be extended or modified by adding new files to the `strategy/` folder.

---
See `engine/`, `risk/`, and `data/` docs for supporting logic.