# MiroFish Integration (Phase 3)

This document describes the current MiroFish integration in TradeCraft.

## What Was Added

- Backend config flags for MiroFish sidecar connectivity and fail-open behavior.
- A dedicated service client: `backend/app/services/mirofish_service.py`.
- Bridge endpoints under `"/api/v1/mirofish"` for simulation/report lifecycle calls.
- Advisory orchestration endpoint that triggers generate + polls + fetches + normalizes.
- Advisory persistence table: `mirofish_advisories` (migration `004_mirofish_advisories`).
- Trade API normalized proxy endpoint for n8n consumption.
- n8n policy gate inserted before risk check in active workflow.
- Trade API advisory observability endpoint for status/latency counters.
- Trade API watchlist refresh endpoint for scheduled advisory snapshots.
- Frontend dashboard advisory card for latest MiroFish snapshot.

## Safety Design

- Integration is disabled by default (`MIROFISH_ENABLED=false`).
- Fail-open mode is enabled by default (`MIROFISH_FAIL_OPEN=true`).
- No order execution path depends on MiroFish responses.

## Environment Variables

Add these values in `.env` (already documented in `.env.example`):

```env
MIROFISH_ENABLED=false
MIROFISH_BASE_URL=http://localhost:5001
MIROFISH_API_PREFIX=/api
MIROFISH_TIMEOUT_SECONDS=30
MIROFISH_FAIL_OPEN=true
MIROFISH_API_KEY=
```

## Deployment Checklist

- Run DB migration before calling advisory endpoints:
  - `docker-compose exec backend alembic upgrade head`
- Set `MIROFISH_ENABLED=true` in runtime `.env` when sidecar is reachable.
- If backend runs inside Docker and MiroFish runs on host (Windows/Mac), prefer:
  - `MIROFISH_BASE_URL=http://host.docker.internal:5001`

## New Endpoints

Base path: `"/api/v1/mirofish"`

- `GET /health`
- `POST /simulation/create`
- `POST /simulation/prepare`
- `POST /simulation/start`
- `POST /report/generate`
- `POST /report/status`
- `GET /report/by-simulation/{simulation_id}`
- `POST /advisory/run`
- `GET /advisory/latest`

Trade API normalized endpoints (`project-name]/src/app.ts`):

- `POST /api/mirofish/advisory`  (run orchestration and return normalized output)
- `GET /api/mirofish/advisory`   (fetch latest stored normalized advisory)
- `POST /api/mirofish/advisory/refresh-watchlist` (refresh snapshots for multiple symbols)
- `GET /api/mirofish/metrics` (advisory request counters and latency)

All endpoints return a standardized shape:

```json
{
  "ok": true,
  "status": "success",
  "message": "MiroFish request completed",
  "source": "mirofish",
  "degraded": false,
  "data": {},
  "error": null
}
```

In fail-open mode, connectivity errors return `status=degraded` with `ok=false` and do not crash caller flow.

## Normalized Advisory Shape

The trade-api endpoint returns:

```json
{
  "success": true,
  "degraded": false,
  "simulation_id": "sim_xxxx",
  "symbol": "NIFTY",
  "status": "completed",
  "advisory": {
    "scenario_bias": "risk_on",
    "tail_risk_score": 0.31,
    "narrative_confidence": 0.74,
    "summary": "..."
  },
  "source": "tradecraft-mirofish-bridge",
  "raw": {}
}
```

## Phase 3 Rollout Status

- n8n gate added in active workflow (`.active_compound.json`):
  - `AI Approved?` -> `Get MiroFish Advisory` -> `Build Advisory Gate` -> `Advisory Approved?`
  - Trade is blocked when:
    - `tail_risk_score >= 0.70`
    - `scenario_bias = risk_off` and AI `confidence < 8`
- New Telegram alert node: `Telegram Advisory Block Alert`.
- Nightly branch now includes `Refresh Advisory Watchlist` before consolidation.
- Frontend now shows `MiroFishAdvisoryCard` on dashboard.

## Scheduling and Mapping

Set one of these in `.env` for scheduled refresh:

```env
MIROFISH_SIMULATION_ID=sim_default
MIROFISH_SYMBOL_SIMULATION_MAP={"NIFTY":"sim_nifty","BANKNIFTY":"sim_banknifty"}
```

`POST /api/mirofish/advisory/refresh-watchlist` accepts optional override payload:

```json
{
  "symbols": ["NIFTY", "BANKNIFTY"],
  "default_simulation_id": "sim_default",
  "simulation_map": { "NIFTY": "sim_nifty" },
  "wait_timeout_seconds": 45,
  "poll_interval_seconds": 5,
  "store_result": true
}
```

## Practical Example

PowerShell request to run normalized advisory orchestration:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:3001/api/mirofish/advisory" `
  -ContentType "application/json" `
  -Body '{"simulation_id":"sim_xxxx","symbol":"NIFTY","wait_timeout_seconds":90}'
```
