# Track 2 Compliance — Requirement Map

**How to read this page.** Every Track 2 requirement is mapped to the exact
implementation (file/endpoint) and the evidence that proves it (test suite,
verify script, measured output). Nothing here is aspirational — every row
points at code in this repo and a check that exercises it. The 30-second
version is [`JUDGES_CHEAT_SHEET.md`](../JUDGES_CHEAT_SHEET.md).

Status legend: **✅ met** (implemented + verified), **🟡 partial** (implemented,
live-data caveat documented).

---

## A. Return-risk scoring (the hero — pre-shipping decision)

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| A1 | Score an order **before dispatch** and return an actionable tier | `POST /v1/return/score` → `return_risk/scorer.py` (`LOW/MEDIUM/HIGH` + action + recommendations) | `tests/integration/test_return_risk_api.py`, `tests/unit/return_risk/test_scorer.py`; live check `verify_live_stack.py` (honest → LOW 0.03, serial → HIGH 0.94) |
| A2 | Learn from data, not just rules — a real model as the primary engine | XGBoost primary (`return_risk/scorer.py`), trained by `scripts/train_xgb_return_risk.py`, transparent hand-weighted fallback | `--full-verify` checks 3–5 (Premium PR-AUC ≥0.94, ROC ≥0.92, Enriched ≥0.88) |
| A3 | Features come from real user history, not placeholders | `return_risk/feature_engine.py` reads Redis profiles/velocity/merchant baselines; every feature carries a `source` tag | `tests/unit/return_risk/test_feature_engine.py` (provenance assertions), `tests/unit/test_redis_clients.py` |
| A4 | Explainability: show *why* a score is what it is | `feature_breakdown` (value/normalized/weight/contribution/source) + `rules_triggered` + `recommendations` in every response | `test_scorer.py::test_feature_provenance_in_breakdown`, `test_contributions_sum_to_score` |
| A5 | Domain rules complement the model (config-driven, hot-reload) | `return_risk/rules_engine.py` + `configs/return_risk_rules.yaml` (9 rules) | `tests/unit/return_risk/test_rules_engine.py` |
| A6 | Ground truth loop: record actual returns as labels for retraining | `POST /v1/return/update` + `/webhooks/razorpay/refund` → Redis `return_risk:labels` → nightly retrain path | `tests/integration/test_razorpay_webhooks.py` (label persistence), `tests/unit/test_ab_return_risk.py` |
| A7 | Honest model evidence, not aspirational numbers | ROC-AUC measured via `roc_auc_score`; ablation (LOFO) proves each feature; base generator git-guarded | `--full-verify` checks 1 (base-gen untouched), 10 (ablation baseline 0.8087), 7 (no hardcoded fallbacks) |

> **Scope:** Track 2 is the **return-risk** surface. The repo also contains
> fraud (`engine/`, `ml/`) and chargeback (`chargeback/`) extensions from
> earlier platform work — they remain in the codebase but are **out of scope
> for this track** and therefore not mapped here (see README → Repository
> Scope for the honest accounting).

## B. Razorpay platform integration

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| B1 | Pre-ship hook for a merchant's `order.paid` | `/webhooks/razorpay/return-risk` (HMAC-verified) → `integrations/razorpay_adapter.py` (paise→₹, method→enum, notes→features) | `tests/integration/test_razorpay_webhooks.py`, `tests/unit/test_razorpay_adapter.py` |
| B2 | `refund.processed` becomes a training label | `/webhooks/razorpay/refund` → `return_risk:labels` | `test_razorpay_webhooks.py::test_refund_processed_records_label` |
| B3 | Order/payment/refund client for reconciliation & backfill | `integrations/razorpay_orders_client.py` (test-mode, HTTP Basic auth, mock-mode default) | `docs/RAZORPAY_INTEGRATION.md`; live keys verified against `api.razorpay.com/v1` |
| B4 | No secrets in the repo | Credentials only via env (`RAZORPAY_*`); `.env` git-ignored | `CONTRIBUTING.md` §secrets; `git ls-files` shows no `.env` |

## C. Governance, compliance & explainability

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| C1 | Tamper-evident, PII-masked audit trail of decisions | `store/audit_log.py` (hash-chained JSONL + PII masking) | `tests/unit/chargeback/test_audit_log_reader.py`, `tests/unit/test_security_hardening.py` |
| C2 | Role-based access control on sensitive surfaces | `api/rbac.py` + `configs/rbac.yaml` (`return_risk:read`, `return_risk:write`, …) | `tests/integration/test_security_api.py`; live check RBAC 403 paths |
| C3 | Encryption at rest for payment data | AES-256 (`ENCRYPTION_KEY` env), dev-only default with prod rotation note | `tests/unit/test_security_hardening.py`, `.env.example` |
| C4 | Decision explanations persisted to the audit chain | Every `RETURN_RISK_SCORED` event carries the score, tier, order/merchant, and the full feature breakdown is recoverable from the chain | `tests/unit/chargeback/test_audit_log_reader.py`, `test_return_risk_api.py` |
| C5 | Drift monitoring so model degradation is visible | `/admin/drift/return-risk` + PSI estimator (43.4 → 3.86 after fix) | `tests/unit/test_drift.py`, `test_drift_report.py`; live check `/admin/drift/return-risk → 200` |
| C6 | Regional compliance (data region, no cross-border replication by default) | `DATA_REGION=IN`, `CROSS_BORDER_REPLICATION=false` in env/config | `docs/COMPLIANCE_DELTA.md`, `configs/config.yaml` |

## D. Evidence integrity & reproducibility

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| D1 | All headline numbers reproduce from one command | `python scripts/run_all_scenarios.py --full-verify` → 12/12 PASS | `reports/full_verify_output.txt` (committed) |
| D2 | Byte-identical training (no unseeded RNG, no timestamps) | Determinism check: train × 3 twice, byte-compare result JSONs | `--full-verify` check 2 |
| D3 | Docs stay in lockstep with measured numbers | `docs/_number_manifest.json` + `scripts/verify_doc_consistency.py` | `--full-verify` check 8 |
| D4 | Live Docker stack passes its curated scenarios | `scripts/seed_demo_data.py` + `scripts/verify_live_stack.py` → 11/11 PASS | Live run (honest LOW 0.03, serial HIGH 0.94, burst BLOCK) |
| D5 | Cost model is derived from measured operating points, never hardcoded | `docs/cost_model/calculator.py` (no-fallback), `--full-verify` check 7 | `tests/unit/test_cost_model.py` (₹17.4L pinned) |
| D6 | Fixed, wheel-universal ML stack for cross-platform reproducibility | `requirements.txt` pins numpy/pandas/scipy/sklearn/xgboost for Python 3.11 (macOS + Linux) | `--full-verify` on a fresh clone reproduces byte-identical numbers |
| D7 | Feature-waterfall explainability — show *why* a score is what it is | `POST /v1/return/explain` (per-feature gain importance × value, neutral base 0.5) | `tests/integration/test_return_risk_api.py::TestReturnRiskExplain`; dashboard Model Waterfall section |
| D8 | Abuse-ring sentinel — coordinated-abuse detection, defense-only | `return_risk/feature_engine.py` address-hash tracking + `R-RULE-09` score-floor override (0.85) | `tests/unit/return_risk/test_scorer.py` (ring → HIGH; family co-shipping → no false positive); live demo seeds a 4-user ring |
| D9 | Temporal integrity — no look-ahead bias in DGP features or split | `scripts/verify_temporal_integrity.py` (chronology + split leakage + latent-sampled first-order features), wired as `--full-verify` check 11 | `--full-verify` → 12/12 PASS |
| D10 | Human-in-the-loop review queue — MEDIUM decisions surfaced for operators | `GET/POST /v1/meta/review-queue` (audit-chain backed, reviewed flag in Redis) + dashboard `/review-queue` | `tests/integration/test_review_queue.py`; live smoke (mark → reflected) |
| D11 | Guided demo tour — 10-minute judge walkthrough | `GET /v1/meta/demo/guide` + dashboard `/demo-tour` (auto-navigating stops) | `tests/integration/test_track2_compliance.py::TestDemoGuide` |
| D12 | Calibration simulator — interactive feature sliders, basic vs premium model | `POST /v1/return/simulate` + dashboard `/simulator` | `tests/integration/test_return_risk_api.py::TestReturnRiskSimulate`; live (basic 7-feature vs premium 9-feature) |
| D13 | Live scorer runs a model trained on the live feature pipeline | `models/return_risk_xgb_live.json` (test PR-AUC 0.8227, ROC-AUC 0.8082) via `scripts/train_live_features.py`; wired as `--full-verify` check 12 (deterministic re-train + PR-AUC ≥ 0.82) | `--full-verify` check 12; live run 11/11 |

---

## Verified totals

- **Hermetic ML suite:** `--full-verify` → **12/12 PASS** (base-gen integrity, byte-identical determinism — DGP and live-features models, AUC gates, ₹ gates, no-hardcoded-fallbacks, doc & dashboard consistency, ablation baseline, temporal integrity, live-model PR-AUC gate).
- **Live Docker stack:** `verify_live_stack.py` → **11/11 PASS**.
- **Compliance map:** **16/16 return-risk requirements verified** (`GET /v1/meta/track2-compliance`).
- **Test suite:** `pytest tests/` → **498 passed, 1 skipped** (47 test modules incl. return-risk, abuse-ring, explain, review-queue, simulator).

## Honest gaps (documented, not hidden)

1. **Synthetic labels.** Labels come from a calibrated DGP, not real merchant data.
2. **No live pilot yet.** The 0.50 gate and base-rate calibration are projections; the Phase-2 pilot (1,000 real orders) in `REAL_DATA_ROADMAP.md` validates them.
3. **Real-label calibration pending.** The live scorer now runs a model *trained on the live feature pipeline* (distribution gap closed), but the final calibration to real merchant labels is the next step.
4. **Razorpay disputes live codec pending.** Schema tested against the real API surface; live dispute payloads not yet exercised (no disputes exist on the test account).

_Map: [`docs/TRACK2_ARCHITECTURE.md`](TRACK2_ARCHITECTURE.md) · Evidence: [`reports/full_verify_output.txt`](../reports/full_verify_output.txt) · Defense: [`docs/INTERVIEW_DEFENSE.md`](INTERVIEW_DEFENSE.md)_
