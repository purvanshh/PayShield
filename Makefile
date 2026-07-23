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
	mypy api/ engine/ llm/ data/ store/ observability/

pre-commit:
	pre-commit run --all-files

pre-commit-install:
	pre-commit install

# Training & Evaluation
train:
	python scripts/train_gnn.py --epochs 50

evaluate:
	python scripts/evaluate.py

benchmark:
	python scripts/benchmark_latency.py --n-requests 500

backtest:
	python scripts/backtest.py --days 7 --daily-txns 1000

ablation:
	python scripts/ablation.py

sensitivity:
	python scripts/sensitivity.py

generate-data:
	python scripts/generate_synthetic_data.py

validate-data:
	python scripts/validate_data.py

# Environment
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/
