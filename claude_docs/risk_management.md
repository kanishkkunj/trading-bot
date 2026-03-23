# Risk Management

This file explains the risk management logic in the application.

## Location
- Risk logic is in `backend/app/risk/` and `engine/policy.py`.

## Key Features
- **Position Sizing**: Determines how much to trade based on risk.
- **Stop-Loss**: Sets automatic sell points to limit losses.
- **Portfolio Risk**: Calculates overall portfolio exposure.
- **Risk Policies**: Enforced via `policy.py`.

## Integration
- Risk checks are performed before every trade.
- Strategies and execution modules use risk management functions.

---
See strategy and engine docs for more details.