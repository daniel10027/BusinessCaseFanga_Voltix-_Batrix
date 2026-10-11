.PHONY: install lint format typecheck test-unit test-integration test-e2e test up down demo migrate

PYTHON ?= python3.12
VENV := .venv
BIN := $(VENV)/bin

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: $(VENV)/bin/activate
	$(BIN)/pip install -e ".[dev]"

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

format:
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

typecheck:
	$(BIN)/mypy
	$(BIN)/lint-imports

test-unit:
	$(BIN)/pytest tests/unit --cov --cov-report=term-missing

test-integration:
	$(BIN)/pytest tests/integration

test-e2e:
	$(BIN)/pytest tests/e2e

test: lint typecheck test-unit test-integration

up:
	docker compose up --build

down:
	docker compose down -v

demo:
	$(BIN)/python scripts/run_demo.py

migrate:
	$(BIN)/alembic -c src/fanga_ingest/adapters/persistence/alembic.ini upgrade head
