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

# SRE & Chaos
chaos-test:
	python scripts/chaos-run.py list

chaos-run:
	python scripts/chaos-run.py run $(experiment)

# CI/CD
ci:
	pip install -r requirements-dev.txt
	make lint
	make test
	make typecheck

security-scan:
	bandit -r api/ agents/ ml/ llm/ engine/ -f json -o reports/security-scan.json || true

# Model A/B Testing & Continuous Improvement
trigger-retrain:
	python -c "from ml.continuous_improvement import ContinuousImprovementLoop; loop = ContinuousImprovementLoop(); report = loop.check_retrain_trigger(); print(report); exit(0 if report['should_retrain'] else 1)" || echo "Retraining not needed"

# Compliance
compliance-check:
	python -c "from compliance.pci_dss import PCIDSSComplianceChecker; c=PCIDSSComplianceChecker(); r=c.run(); print(f'PCI-DSS: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"
	python -c "from compliance.rbi_localization import RBILocalizationChecker; c=RBILocalizationChecker(); r=c.run(); print(f'RBI: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"
	python -c "from compliance.eu_ai_act import EUAiActComplianceChecker; c=EUAiActComplianceChecker(); r=c.run(); print(f'EU AI Act: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"

compliance-report:
	python -c "from compliance.audit_generator import ComplianceAuditGenerator; g=ComplianceAuditGenerator(); r=g.generate_quarterly_report(); print(f'Report: {r.report_id}, score={r.score}')"

compliance-evidence:
	python -c "from compliance.evidence_collector import EvidenceCollector; c=EvidenceCollector(); p=c.collect_evidence(); print(f'Evidence: {p}')"

experiment-list:
	python -c "from ml.ab_testing import ABTestFramework; f = ABTestFramework(); [print(e.name, e.status, e.traffic_split) for e in f.list_experiments()]"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/
