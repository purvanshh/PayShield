.PHONY: up down build test lint format typecheck pre-commit clean demo-stack demo-health demo-prewarm demo-normal demo-burst demo-geo demo-investigation demo-drift

# Docker
up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

build:
	docker compose -f docker/docker-compose.yml build

# Demo replay
demo-stack:
	bash scripts/demo_replay.sh stack

demo-health:
	bash scripts/demo_replay.sh health

demo-prewarm:
	bash scripts/demo_replay.sh prewarm $(if $(SUFFIX),$(SUFFIX),DEMO)

demo-normal:
	bash scripts/demo_replay.sh normal $(if $(SUFFIX),$(SUFFIX),DEMO)

demo-burst:
	bash scripts/demo_replay.sh burst $(if $(SUFFIX),$(SUFFIX),DEMO)

demo-geo:
	bash scripts/demo_replay.sh geo

demo-investigation:
	bash scripts/demo_replay.sh investigation $(if $(TXN_ID),$(TXN_ID),TXN_BURST_$(if $(SUFFIX),$(SUFFIX),DEMO)_14)

demo-drift:
	bash scripts/demo_replay.sh drift

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

# Phase 10 — benchmark a retrained candidate, gate it against the currently
# promoted model, and register+promote only when it improves by >= 0.005 PR-AUC.
retrain:
	python scripts/benchmark_gnn.py --users 12000 --merchants 1000 --txns 36000 --epochs 100 --batch-size 16 --sweep-trials 8 --sweep-epochs 25 --latency-runs 300 --seed 42 --save-model
	python scripts/check_improvement.py --epsilon 0.005 --register-if-better

retrain-gate:
	python scripts/check_improvement.py --epsilon 0.005

# Compliance
compliance-check:
	python -c "from compliance.pci_dss import PCIDSSComplianceChecker; c=PCIDSSComplianceChecker(); r=c.run(); print(f'PCI-DSS: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"
	python -c "from compliance.rbi_localization import RBILocalizationChecker; c=RBILocalizationChecker(); r=c.run(); print(f'RBI: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"
	python -c "from compliance.eu_ai_act import EUAiActComplianceChecker; c=EUAiActComplianceChecker(); r=c.run(); print(f'EU AI Act: score={r.score}, passed={r.passed}, findings={len(r.findings)}')"

compliance-report:
	python -c "from compliance.audit_generator import ComplianceAuditGenerator; g=ComplianceAuditGenerator(); r=g.generate_quarterly_report(); print(f'Report: {r.report_id}, score={r.score}')"

compliance-evidence:
	python -c "from compliance.evidence_collector import EvidenceCollector; c=EvidenceCollector(); p=c.collect_evidence(); print(f'Evidence: {p}')"

# Phase 60 — Health & Architecture
health-report:
	python scripts/system_health_report.py

benchmark-opt:
	python scripts/benchmark_optimization.py

arch-review:
	@echo "=== Architecture Review (Phase 60) ==="
	@echo "See ARCHITECTURE_REVIEW.md for full document"
	@echo "Review checklist:"
	@echo "  - [ ] READ ARCHITECTURE_REVIEW.md"
	@echo "  - [ ] REVIEW PERFORMANCE_OPTIMIZATION_LOG.md"
	@echo "  - [ ] UPDATE TECHNICAL_DEBT_REGISTER.md"
	@echo "  - [ ] CHECK MAINTENANCE_ROADMAP.md"
	@echo "  - [ ] VERIFY CURRENT METRICS IN models/gnn_benchmark_results.json"

experiment-list:
	python -c "from ml.ab_testing import ABTestFramework; f = ABTestFramework(); [print(e.name, e.status, e.traffic_split) for e in f.list_experiments()]"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/
