# Testing & Scripts

This file explains the testing and scripting setup.

## Location
- Tests are in `backend/tests/`.
- Scripts are in `backend/scripts/` and root `scripts/`.

## Testing
- **Unit Tests**: Test individual modules (auth, data ingestion, features, orders, risk, strategy, etc.).
- **Integration Tests**: Test interactions between modules.
- **conftest.py**: Test configuration and fixtures.

## Scripts
- **reset_paper.py**: Resets paper trading environment.
- **train_model.py**: Trains ML models.
- **bootstrap.sh**: Sets up environment.
- **download_historical.py**: Downloads historical data.
- **health_check.py**: Checks system health.
- **seed_data.py**: Seeds database with initial data.

---
See ML and backend docs for more details.