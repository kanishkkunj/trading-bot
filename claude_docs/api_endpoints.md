# API Endpoints

This file explains the REST API endpoints provided by the backend.

## Location
- Endpoints are defined in `backend/app/api/` modules.

## Main Endpoints
- **admin.py**: Admin operations
- **auth.py**: Authentication (login, register)
- **backtest.py**: Backtesting strategies
- **market.py**: Market data access
- **orders.py**: Order placement and management
- **paper.py**: Paper trading
- **portfolio.py**: Portfolio management
- **risk.py**: Risk management
- **signals.py**: Trading signals
- **strategy.py**: Strategy management
- **ws.py**: WebSocket for real-time updates

## How Endpoints Work
- Each module defines FastAPI routes for its domain.
- Endpoints interact with engine, data, broker, and risk modules.
- Authentication and authorization are handled in `auth.py`.

---
See backend overview and strategy docs for more details.