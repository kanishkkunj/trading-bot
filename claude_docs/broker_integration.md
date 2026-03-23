# Broker Integration

This file explains how the application integrates with brokers.

## Location
- Broker logic is in `backend/app/broker/`.

## Supported Brokers
- **Zerodha**: Real trading via `zerodha.py` and `zerodha_client.py`.
- **Paper Broker**: Simulated trading via `paper.py`.

## How Integration Works
- Each broker module implements a base interface (`base.py`).
- Orders are routed through broker modules from strategies and API endpoints.
- Clients for external APIs are in `clients/`.

## Extending Brokers
- Add new broker modules to `broker/` and implement the base interface.

---
See engine and strategy docs for order flow.