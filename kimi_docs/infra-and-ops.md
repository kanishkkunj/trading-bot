# Infra & Ops

## Docker Compose
- Services: `postgres` (Timescale), `redis`, `backend` (uvicorn reload), `frontend` (Next dev). Ports: 5432, 6379, 8000, 3000.
- Volumes: postgres_data, redis_data; backend/frontend bind mounts for live code reload.

## Dockerfile (backend)
- Python 3.11-slim, installs editable package via `pyproject.toml`, runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

## Env Vars
- `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALGORITHM`, token expiries, `PAPER_INITIAL_CAPITAL`, Cognee: `COGNEE_API_KEY`, `COGNEE_BASE_URL`, Zerodha: `ZERODHA_API_KEY/SECRET`, frontend: `NEXT_PUBLIC_API_URL`.

## Scripts
- `scripts/bootstrap.sh`: setup helper.
- `scripts/download_historical.py`, `train_model.py`, `seed_data.py`, `health_check.py` (root-level utilities).
- `backend/scripts/reset_paper.py`: clean paper trading data for a user.

## Running Locally
- Backend: `docker-compose up backend` (or `uvicorn backend.app.main:app --reload --port 8000` with venv + deps).
- Frontend: `npm install`, `npm run dev -- --port 3002` (avoid busy 3000/3001); set `NEXT_PUBLIC_API_URL=http://localhost:8000`.

## Testing
- Backend: `pytest backend/tests`.
- Frontend: (no configured test suite) — rely on React Query/TypeScript for type safety.

## Logging/Monitoring
- Backend logs to stdout (uvicorn + structlog in code). Cognee failures fail-soft (print). DB uses SQLAlchemy logging in debug mode (visible in container logs).

## CORS
- Allowed origins: localhost/127.0.0.1 on 3000/3001/5173; wildcard regex enabled; credentials allowed.
