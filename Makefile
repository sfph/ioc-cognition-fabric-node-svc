# =========================
# ioc-cognition-fabric-node-svc
# =========================

.PHONY: help install run run-dev test test-cov lint clean docs

PYTHON := python
POETRY := poetry
APP_MODULE := src.app.main:app
PORT ?= 9002
OPENAPI_OUT ?= docs/openapi.json

help:
	@echo "Available commands:"
	@echo "  make install     Install dependencies using Poetry"
	@echo "  make run         Run the service"
	@echo "  make run-dev     Run the service with auto-reload"
	@echo "  make test        Run unit tests"
	@echo "  make test-cov    Run tests with coverage"
	@echo "  make docs     	  Generate docs/openapi.json"
	@echo "  make clean       Remove cache and build artifacts"

install:
	$(POETRY) install --no-root

lint:
	./scripts/lint.sh

run:
	$(POETRY) run python -m src.app.main

run-dev:
	$(POETRY) run uvicorn $(APP_MODULE) --host 0.0.0.0 --port $(PORT) --reload

test:
	$(POETRY) run pytest --ignore=tests/integration

test-cov:
	$(POETRY) run pytest --ignore=tests/integration --cov=src --cov-report=term-missing

docs:
	@mkdir -p $(dir $(OPENAPI_OUT))
	@$(POETRY) run $(PYTHON) -c 'import json; from src.app.main import create_app; print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))' > $(OPENAPI_OUT)
	@echo "Wrote $(OPENAPI_OUT)"

clean:
	rm -rf .pytest_cache .coverage __pycache__ .mypy_cache
