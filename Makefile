.PHONY: help up down test lint migrate seed demo loadtest fmt typecheck

help:
	@echo "BIP Development Targets"
	@echo "  up         - Start all services via docker compose"
	@echo "  down       - Stop all services"
	@echo "  test       - Run test suite"
	@echo "  lint       - Run ruff linter"
	@echo "  fmt        - Run ruff formatter"
	@echo "  typecheck  - Run mypy strict on sdk and core"
	@echo "  migrate    - Run alembic migrations"
	@echo "  seed       - Seed dev data"
	@echo "  demo       - Full demo: services + emulators + webhook receiver"
	@echo "  loadtest   - Run 2000-device load test"

up:
	docker compose up -d --build
	@echo "Waiting for services..."
	docker compose ps

down:
	docker compose down

test:
	python -m pytest tests/ -v --tb=short -m "not e2e"

test-all:
	python -m pytest tests/ -v --tb=short

lint:
	python -m ruff check src/ tests/ clients/
	python -m ruff format --check src/ tests/ clients/

fmt:
	python -m ruff check --fix src/ tests/ clients/
	python -m ruff format src/ tests/ clients/

typecheck:
	python -m mypy src/bip/sdk src/bip/core --strict

migrate:
	python -m alembic upgrade head

seed:
	python -m bip.core.seed

demo:
	@echo "Starting demo environment..."
	docker compose up -d --build
	@echo "Waiting for services to be healthy..."
	sleep 10
	python -m bip.emulators.adms --devices 5 --server http://localhost:8081 &
	python -m bip.emulators.webhook_receiver --port 9090 &
	@echo "Demo running. Punches will appear shortly."
	@echo "Press Ctrl+C to stop."

loadtest:
	python -m bip.emulators.loadtest --devices 2000 --minutes 10
