# TradeCraft

Algorithmic trading platform for Indian stock markets (NIFTY50).

## Features

- **ML-Powered Strategy Engine**: XGBoost/LightGBM models with rule-based filters
- **Backtesting**: Walk-forward validation with realistic fees and slippage
- **Paper Trading**: Test strategies without real money
- **Live Trading**: Zerodha Kite Connect integration
- **Risk Management**: Position sizing, daily loss limits, kill switch
- **Real-time Dashboard**: Next.js frontend with live PnL tracking

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd tradecraft
cp .env.example .env

# 2. Start with Docker
docker-compose up -d

# 3. Run migrations
docker-compose exec backend alembic upgrade head

# 4. Seed sample data
docker-compose exec backend python scripts/seed_data.py

# 5. Access the app
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Development

```bash
# Backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Project Structure

```
tradecraft/
├── frontend/          # Next.js dashboard
├── backend/           # FastAPI backend
├── ml/               # ML experimentation
├── docs/             # Documentation
└── scripts/          # Utility scripts
```

## Sprints

- **Sprint 1**: Foundation (Auth, Data Pipeline, Paper Broker)
- **Sprint 2**: Backtesting & Validation
- **Sprint 3**: Paper Trading Live
- **Sprint 4**: Zerodha Integration
- **Sprint 5**: Production Hardening

## Disclaimer

This is an assistive trading tool, not financial advice. Trading involves risk. Past performance does not guarantee future results.
