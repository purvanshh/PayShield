# Developer Onboarding Guide

## Day 1: Environment Setup

- [ ] Clone repository and install dependencies (`pip install -r requirements.txt -r requirements-dev.txt`)
- [ ] Complete [Getting Started Guide](../guides/getting-started.md)
- [ ] Run the hermetic evidence scripts: `python scripts/train_xgb_return_risk.py`
- [ ] Run the test suite: `make test` (498 tests, no services needed)
- [ ] (Optional) Start the live stack: `docker compose -f docker/docker-compose.yml up -d`

## Day 2: Core Concepts

- [ ] Read [Track 2 Architecture](../TRACK2_ARCHITECTURE.md)
- [ ] Read [Evaluator Guide](../../EVALUATOR_GUIDE.md) — what the submission is judged on
- [ ] Read [API Reference](../API_REFERENCE.md)
- [ ] Score a return-risk order (see Getting Started) and inspect the feature breakdown
- [ ] Explore the codebase structure (`return_risk/` is the evaluated hero)

## Day 3: Development Workflow

- [ ] Create a feature branch
- [ ] Implement a small change (e.g., add a rule to `configs/return_risk_rules.yaml`)
- [ ] Write tests for the change
- [ ] Submit a pull request (follow `CONTRIBUTING.md`)

## Day 4: Verification

- [ ] Run `python scripts/benchmark_return_risk.py` and `python docs/cost_model/calculator.py`
- [ ] Run `python scripts/verify_live_stack.py` against the Docker stack
- [ ] Review the honest ledger: [`MISTAKES_AND_LEARNINGS.md`](../../MISTAKES_AND_LEARNINGS.md)

## Key Resources

### Documentation
- `docs/` — cost model, Razorpay integration, hard bugs, architecture
- `EVALUATOR_GUIDE.md` — the 10-minute walkthrough
- `Makefile` — common commands (`test`, `lint`, `train-xgb`, `ablation-xgb`, `tune-xgb`)
- `CONTRIBUTING.md` — contribution guidelines