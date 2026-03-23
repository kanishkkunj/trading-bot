.PHONY: help setup build up down logs test lint format migrate shell

help:
	@echo "TradeCraft - Algorithmic Trading Platform"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup      - Initial project setup"
	@echo "  make build      - Build all Docker images"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View logs from all services"
	@echo "  make test       - Run all tests"
	@echo "  make lint       - Run linters"
	@echo "  make format     - Format code"
	@echo "  make migrate    - Run database migrations"
	@echo "  make shell      - Open backend shell"

setup:
	@echo "Setting up TradeCraft..."
	cp .env.example .env
	cd backend && pip install -e ".[dev]"
	cd frontend && npm install

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	cd backend && pytest -v
	cd frontend && npm test

lint:
	cd backend && ruff check .
	cd backend && mypy app
	cd frontend && npm run lint

format:
	cd backend && ruff format .
	cd backend && ruff check --fix .
	cd frontend && npm run format

migrate:
	cd backend && alembic upgrade head

shell:
	docker-compose exec backend bash

seed:
	cd backend && python scripts/seed_data.py

health:
	curl http://localhost:8000/api/v1/admin/health
