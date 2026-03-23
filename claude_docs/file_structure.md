# Project File Structure

This document provides a detailed overview of the directory and file structure of the Tradecraft application.

## Root Level
- `docker-compose.yml`, `docker-compose.override.yml`: Docker configuration files for orchestrating backend and frontend services.
- `Makefile`: Automation commands for building, testing, and running the project.
- `README.md`: Project overview and instructions.

## Main Folders
- `backend/`: Python backend application (FastAPI, trading logic, data ingestion, ML, etc.)
- `frontend/`: Next.js frontend application (UI, client logic)
- `kimi_docs/`: Existing documentation
- `scripts/`: Utility scripts for setup, data, and model training

### backend/
- `alembic.ini`: Database migration config
- `Dockerfile`: Backend container config
- `pyproject.toml`: Python project config
- `app/`: Main backend code
  - `alerts/`: Notification modules (email, telegram, whatsapp)
  - `api/`: API endpoints (admin, auth, backtest, market, orders, etc.)
  - `broker/`: Broker integrations (paper, zerodha)
  - `clients/`: Client wrappers (cognee, zerodha)
  - `data/`: Data providers (NSE, yfinance)
  - `data_ingestion/`: Data ingestion logic (market data, options, sentiment)
  - `db/`: Database session and migrations
  - `engine/`: Trading engine, features, models, policies
  - `execution/`, `institutional/`, `ml/`, `models/`, `monitoring/`, `options_analytics/`, `research/`, `risk/`, `schemas/`, `scripts/`, `sentiment/`, `services/`, `strategy/`, `tests/`: Specialized modules
- `scripts/`: Backend scripts (reset, train)
- `tests/`: Backend tests

### frontend/
- `Dockerfile`: Frontend container config
- `src/`: Main frontend code (app, components, hooks, lib, store, types)

### kimi_docs/
- Existing documentation files

### scripts/
- Utility scripts (bootstrap, download, health check, seed, train)

---
See other files in this folder for detailed explanations of each module.