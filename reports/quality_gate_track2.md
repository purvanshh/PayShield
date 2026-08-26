# Track 2 — Quality Gate Report

**Date:** 2026-08-22 · **Branch:** `feature/track2-risk-manager` ·
**Verdict: all gates pass.**

| Gate | Command | Result |
|---|---|---|
| Unit + integration tests | `pytest tests/ -q` | **537 passed, 1 skipped** (16 new suites since Track 1: chargeback/return-risk units, API integration, seeder, flow) |
| Coverage — whole suite | `pytest tests/ --cov` | **76.4%** (gate ≥ 70%) |
| Coverage — track-2 modules | targeted cov run | **91.1%** across chargeback/, return_risk/, new routes/schemas |
| Lint | `ruff check chargeback return_risk api/routes/chargeback*.py api/routes/return_risk.py api/schemas api/rbac.py api/exceptions.py`(new dirs) | 0 errors (repo-wide B008 `Depends`-in-default convention is pre-existing and matches `api/routes/score.py` style) |
| Types | `mypy chargeback/ return_risk/ --strict --follow-imports=skip` | **0 errors in 13 source files** — all business logic strictly typed; route modules intentionally follow the repo's existing untyped-FastAPI style (same diagnostics exist for pre-existing `api/routes/score.py`) |
| Security scan | `bandit -r chargeback return_risk` | **0 findings** (4 documented `nosec` annotations: whitelisted-scope eval in the rules engine, deliberate degenerate-path exception handlers, fixture contract assert) |
| Compliance | out of scope for this PoC | no certifications sought — see [`COMPLIANCE_DELTA.md`](../COMPLIANCE_DELTA.md) |
| Bench | `scripts/benchmark_return_risk.py` | PR-AUC 0.9806 / ROC-AUC 0.9846 / P 1.0000 @ HIGH cut / P 0.9444·R 0.9125 @ MEDIUM+ cut |

## Per-module coverage (track-2 surface)

| Module | Coverage | Notes |
|---|---|---|
| `chargeback/evidence_collector.py` | 79% | providers + artifact fallback tested; masking-path guards residual |
| `chargeback/rebuttal_builder.py` | 99% | disposition matrix, urgency, payloads fully covered |
| `chargeback/razorpay_client.py` | 81% | mock + transported modes, error mapping |
| `chargeback/narrative_generator.py` | 90% | disposition + fallback paths |
| `return_risk/feature_engine.py` | 95% | |
| `return_risk/rules_engine.py` | 97% | incl. reload + rule catalogue |
| `return_risk/scorer.py` | 95% | |
| `api/routes/chargeback.py` + `return_risk.py` | covered by API integration suites | auth/RBAC/error paths asserted |

## Build state

- Docker health/tests untouched by this gate (no build run in this env;
  `make typecheck` reports pre-existing gaps in the legacy modules, which
  are out of scope for this gate and unchanged by Track 2 — see note above).
- No secrets: credentials only via env (`RAZORPAY_*`, `PAYSHIELD_DEV_API_KEY`),
  dev key is the documented compose default.
- All gates listed above are reproducible one-liners; the demo data seeder
  and benchmark run fully hermetic (no services required).

## Release marker

Tag `v1.2.0-track2` created at the head of this gate run (local only).
