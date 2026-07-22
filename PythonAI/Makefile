# ═══════════════════════════════════════════════
# PythonAI — Developer Makefile
# ═══════════════════════════════════════════════
# Usage:
#   make help          — Show this help
#   make install       — Install dependencies
#   make dev           — Install dev dependencies (includes lint/test tools)
#   make test          — Run all tests
#   make test-quick    — Run only smoke tests
#   make test-rag      — Run RAG-related tests
#   make test-training — Run training pipeline tests
#   make lint          — Run ruff linter
#   make format        — Auto-format code with ruff
#   make typecheck     — Run mypy type checker
#   make check         — Run lint + typecheck + test
#   make clean         — Clean cache files and build artifacts
#   make rebuild-cache — Clean and rebuild pip cache
#   make serve         — Start FastAPI server (dev mode)
#   make webui         — Start Streamlit Web UI
#   make docker-build  — Build Docker images
#   make docker-up     — Start all Docker services
#   make docker-down   — Stop all Docker services
#   make pre-commit    — Run pre-commit hooks on all files
# ═══════════════════════════════════════════════

.PHONY: help install dev test test-quick test-rag test-training lint format typecheck check clean rebuild-cache serve webui docker-build docker-up docker-down pre-commit

VENV_NAME := .venv
PYTHON := python
PIP := $(PYTHON) -m pip
REQUIREMENTS := requirements.txt
DEV_REQUIREMENTS := requirements-dev.txt

# ═══════════ Colors ═══════════
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
CYAN := \033[0;36m
NC := \033[0m # No Color

help:
	@echo "$(CYAN)╔══════════════════════════════════════════╗"
	@echo "║       PythonAI Developer Commands       ║"
	@echo "╚══════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(YELLOW)Setup:$(NC)"
	@echo "  make install       Install production dependencies"
	@echo "  make dev           Install dev dependencies (lint, test tools)"
	@echo ""
	@echo "$(YELLOW)Testing:$(NC)"
	@echo "  make test          Run all tests (parallel)"
	@echo "  make test-quick    Run only smoke tests"
	@echo "  make test-rag      Run RAG-related tests"
	@echo "  make test-training Run training pipeline tests"
	@echo "  make test-cov      Run tests with coverage report"
	@echo ""
	@echo "$(YELLOW)Code Quality:$(NC)"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Auto-format code with ruff"
	@echo "  make typecheck     Run mypy type checker"
	@echo "  make check         Run lint + typecheck + test (full gate)"
	@echo ""
	@echo "$(YELLOW)Running:$(NC)"
	@echo "  make serve         Start FastAPI server on port 8765"
	@echo "  make webui         Start Streamlit Web UI on port 8501"
	@echo ""
	@echo "$(YELLOW)Docker:$(NC)"
	@echo "  make docker-build  Build Docker images"
	@echo "  make docker-up     Start all Docker services"
	@echo "  make docker-down   Stop all Docker services"
	@echo ""
	@echo "$(YELLOW)Other:$(NC)"
	@echo "  make clean         Clean cache files and build artifacts"
	@echo "  make pre-commit    Run pre-commit hooks on all files"

install:
	@echo "$(CYAN)[Setup] Installing production dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQUIREMENTS)
	@echo "$(GREEN)[OK] Dependencies installed$(NC)"

dev:
	@echo "$(CYAN)[Setup] Installing dev dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r $(REQUIREMENTS)
	$(PIP) install ruff mypy pytest pytest-xdist pytest-cov pre-commit
	@echo "$(GREEN)[OK] Dev dependencies installed$(NC)"

test:
	@echo "$(CYAN)[Test] Running all tests in parallel...$(NC)"
	$(PYTHON) -m pytest tests/ -v --tb=short -n auto
	@echo "$(GREEN)[OK] All tests passed$(NC)"

test-quick:
	@echo "$(CYAN)[Test] Running smoke tests only...$(NC)"
	$(PYTHON) -m pytest tests/ -v --tb=short -n auto -m "smoke"
	@echo "$(GREEN)[OK] Smoke tests passed$(NC)"

test-rag:
	@echo "$(CYAN)[Test] Running RAG tests...$(NC)"
	$(PYTHON) -m pytest tests/ -v --tb=short -m "rag" -n auto
	@echo "$(GREEN)[OK] RAG tests passed$(NC)"

test-training:
	@echo "$(CYAN)[Test] Running training tests...$(NC)"
	$(PYTHON) -m pytest tests/ -v --tb=short -m "training" -n auto
	@echo "$(GREEN)[OK] Training tests passed$(NC)"

test-cov:
	@echo "$(CYAN)[Test] Running tests with coverage...$(NC)"
	$(PYTHON) -m pytest tests/ -v --tb=short -n auto --cov=src --cov-report=term-missing --cov-report=html
	@echo "$(GREEN)[OK] Coverage report generated$(NC)"

lint:
	@echo "$(CYAN)[Lint] Running ruff linter...$(NC)"
	$(PYTHON) -m ruff check src/ tests/
	@echo "$(GREEN)[OK] Lint passed$(NC)"

format:
	@echo "$(CYAN)[Format] Auto-formatting with ruff...$(NC)"
	$(PYTHON) -m ruff format src/ tests/
	@echo "$(GREEN)[OK] Format complete$(NC)"

typecheck:
	@echo "$(CYAN)[TypeCheck] Running mypy...$(NC)"
	$(PYTHON) -m mypy src/
	@echo "$(GREEN)[OK] Type check passed$(NC)"

check: lint typecheck test
	@echo "$(GREEN)╔══════════════════════════════════════╗"
	@echo "║   All checks passed! Ready to ship.   ║"
	@echo "╚══════════════════════════════════════════╝$(NC)"

clean:
	@echo "$(CYAN)[Clean] Removing cache and build artifacts...$(NC)"
	python -c "import shutil, os, pathlib; root=pathlib.Path('.'); \
		cnt=0; \
		for p in root.rglob('__pycache__'): shutil.rmtree(p, ignore_errors=True); cnt+=1; \
		for p in root.rglob('.pytest_cache'): shutil.rmtree(p, ignore_errors=True); cnt+=1; \
		for p in root.rglob('.ruff_cache'): shutil.rmtree(p, ignore_errors=True); cnt+=1; \
		for p in root.rglob('*.egg-info'): shutil.rmtree(p, ignore_errors=True); cnt+=1; \
		for p in root.rglob('htmlcov'): shutil.rmtree(p, ignore_errors=True); cnt+=1; \
		for p in root.rglob('*.pyc'): p.unlink(missing_ok=True); cnt+=1; \
		for p in root.rglob('*.pyo'): p.unlink(missing_ok=True); cnt+=1; \
		if root.joinpath('.coverage').exists(): root.joinpath('.coverage').unlink(); \
		print(f'Cleaned {cnt} items')"
	@echo "$(GREEN)[OK] Clean complete$(NC)"

rebuild-cache:
	@echo "$(CYAN)[Cache] Rebuilding pip cache...$(NC)"
	$(PIP) cache purge
	@echo "$(GREEN)[OK] Cache cleared$(NC)"

serve:
	@echo "$(CYAN)[Serve] Starting FastAPI server...$(NC)"
	$(PYTHON) -m src.cli serve --host 0.0.0.0 --port 8765

webui:
	@echo "$(CYAN)[WebUI] Starting Streamlit dashboard...$(NC)"
	$(PYTHON) -m streamlit run src/webui/app.py --server.port 8501

docker-build:
	@echo "$(CYAN)[Docker] Building images...$(NC)"
	docker compose build
	@echo "$(GREEN)[OK] Docker images built$(NC)"

docker-up:
	@echo "$(CYAN)[Docker] Starting services...$(NC)"
	docker compose up -d
	@echo "$(GREEN)[OK] Docker services started$(NC)"

docker-down:
	@echo "$(CYAN)[Docker] Stopping services...$(NC)"
	docker compose down
	@echo "$(GREEN)[OK] Docker services stopped$(NC)"

pre-commit:
	@echo "$(CYAN)[Pre-commit] Running hooks on all files...$(NC)"
	pre-commit run --all-files
	@echo "$(GREEN)[OK] Pre-commit hooks passed$(NC)"
