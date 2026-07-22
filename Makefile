.PHONY: up down build test lint clean

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

build:
	docker compose -f docker/docker-compose.yml build

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

test-load:
	locust -f tests/load/locustfile.py --headless -u 50 -r 10 --run-time 60s

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

lint:
	ruff check . --fix

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
