# =========================
# ioc-cognition-fabric-node-svc
# =========================

.PHONY: help install run run-dev test test-cov lint clean

PYTHON := python
POETRY := poetry
APP_MODULE := src.app.main:app
PORT ?= 9002

help:
	@echo "Available commands:"
	@echo "  make install     Install dependencies using Poetry"
	@echo "  make run         Run the service"
	@echo "  make run-dev     Run the service with auto-reload"
	@echo "  make test        Run unit tests"
	@echo "  make test-cov    Run tests with coverage"
	@echo "  make clean       Remove cache and build artifacts"

install:
	$(POETRY) install

run:
	$(POETRY) run python src/app/main.py

run-dev:
	$(POETRY) run uvicorn $(APP_MODULE) --host 0.0.0.0 --port $(PORT) --reload

test:
	$(POETRY) run pytest

test-cov:
	$(POETRY) run pytest --cov=src --cov-report=term-missing

clean:
	rm -rf .pytest_cache .coverage __pycache__ .mypy_cache
