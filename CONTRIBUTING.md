# Contributing to PayShield

Thanks for wanting to help. PayShield is a three-layer risk platform (L1
statistical rules, L2 GNN, L3 LLM investigation) extended by Track 2 with a
chargeback evidence responder and a return-risk scorer — all defence-only,
all explainable, all measured.

## Quick start

```bash
# 1. Fork and clone
git clone git@github.com:<you>/PayShield.git
cd PayShield

# 2. Set up the environment (Python 3.11+)
pip install -r requirements.txt -r requirements-dev.txt

# 3. Run the suite — everything below must pass before you open a PR
make test          # 537 tests, hermetic (no Redis/Neo4j/Ollama required)
```

## Pre-PR checklist

1. Create a feature branch off `feature/track2-risk-manager`:
   `git checkout -b feature/your-change`
2. Make the change. **Add tests** for every new behaviour (unit tests for
   logic, integration tests for API paths — existing patterns in
   `tests/unit/chargeback/`, `tests/integration/test_chargeback_api.py`).
3. Verify the gates for your touched area:

```bash
# Lint (new code must be clean; repo-wide B008 Depends-in-default is
# pre-existing convention and matches api/routes/score.py)
ruff check chargeback return_risk api/routes/chargeback*.py api/routes/return_risk.py

# Types — track-2 business logic must stay strict-clean
mypy chargeback/ return_risk/ --strict --follow-imports=skip --ignore-missing-imports

# Security scan on the risk modules
bandit -r chargeback return_risk

# Targeted tests
pytest tests/unit/chargeback tests/unit/return_risk tests/integration -q
```

4. Update `.env.example`-related docs or `configs/*.yaml` if you change
   behaviour (weights, rules, thresholds are all config — no code changes
   needed for tuning).
5. Commit with a conventional message (`feat:`, `fix:`, `docs:`,
   `chore:` — see git history). Do not mention internal phase numbers.
6. Push and open a PR using the pull request template.

## Code standards

- Python 3.11+, type hints on all public callables
- New feature files include a module docstring; design decisions live in
  `docs/DESIGN_DECISIONS.md` — if you make a trade-off, document it there.
- Pydantic schemas in `api/schemas/`; business logic in `chargeback/` /
  `return_risk/`; routes are thin adapters in `api/routes/`.
- **No secrets or API keys** in commits (env-based config only —
  `RAZORPAY_*`, `PAYSHIELD_DEV_API_KEY`, compose defaults).
- Ever-changing RuleSets: edit `configs/return_risk_rules.yaml` and its
  test, never the conditions inline.
- Compliance must not regress: run the three checkers
  (`make compliance-check`) — results captured in
  `COMPLIANCE_DELTA_TRACK2.md`.

## Getting help

Open an issue for bugs/ideas referencing the affected area
(`chargeback` / `return_risk` / `observability` / `dashboard`). Be specific:
what you observed, expected, and the failing check output.
