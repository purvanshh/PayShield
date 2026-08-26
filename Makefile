.PHONY: up down build test lint format typecheck pre-commit clean

# Docker
up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

build:
	docker compose -f docker/docker-compose.yml build

# Testing
test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

test-load:
	locust -f tests/load/locustfile.py --headless -u 50 -r 10 --run-time 60s

test-cov:
	pytest tests/ --cov --cov-report=term --cov-report=html

# Code Quality
lint:
	ruff check . --fix

format:
	ruff format .

typecheck:
	mypy api/ engine/ data/ store/ observability/

pre-commit:
	pre-commit run --all-files

pre-commit-install:
	pre-commit install

# XGBoost return-risk model pipeline (Phase 1-3)
train-xgb:
	python scripts/train_xgb_return_risk.py

ablation-xgb:
	python scripts/ablation_study.py

tune-xgb:
	python scripts/tune_xgb.py

# Environment
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

# CI/CD
ci:
	pip install -r requirements-dev.txt
	make lint
	make test
	make typecheck

security-scan:
	bandit -r api/ return_risk/ engine/ store/ data/ integrations/ -f json -o reports/security-scan.json || true

# Model A/B Testing & Continuous Improvement
trigger-retrain:
	python -c "from ml.continuous_improvement import ContinuousImprovementLoop; loop = ContinuousImprovementLoop(); report = loop.check_retrain_trigger(); print(report); exit(0 if report['should_retrain'] else 1)" || echo "Retraining not needed"

# Phase 60 — Health & Architecture
health-report:
	python scripts/system_health_report.py

benchmark-opt:
	python scripts/benchmark_optimization.py

arch-review:
	@echo "=== Return-Risk Architecture (Track 02) ==="
	@echo "See docs/TRACK2_ARCHITECTURE.md for the architecture"
	@echo "Review checklist:"
	@echo "  - [ ] READ docs/TRACK2_ARCHITECTURE.md"
	@echo "  - [ ] REVIEW docs/COST_MODEL.md"
	@echo "  - [ ] CHECK CURRENT METRICS IN models/return_risk_benchmark_results.json"

experiment-list:
	python -c "from ml.ab_testing import ABTestFramework; f = ABTestFramework(); [print(e.name, e.status, e.traffic_split) for e in f.list_experiments()]"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/
