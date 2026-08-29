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
| A1 | Score an order **before dispatch** and return an actionable tier | `POST /v1/return/score` → `return_risk/scorer.py` (`LOW/MEDIUM/HIGH` + action + recommendations) | `tests/integration/test_return_risk_api.py`, `tests/unit/return_risk/test_scorer.py`; live check `verify_live_stack.py` (honest → LOW 0.03, serial → HIGH 0.98) |
| A2 | Learn from data, not just rules — a real model as the primary engine | XGBoost primary (`return_risk/scorer.py`), trained by `scripts/train_xgb_return_risk.py`, transparent hand-weighted fallback | `--full-verify` checks 3–5 (Premium PR-AUC ≥0.94, ROC ≥0.92, Enriched ≥0.88) |
| A3 | Features come from real user history, not placeholders | `return_risk/feature_engine.py` reads Redis profiles/velocity/merchant baselines; every feature carries a `source` tag | `tests/unit/return_risk/test_feature_engine.py` (provenance assertions), `tests/unit/test_redis_clients.py` |
| A4 | Explainability: show *why* a score is what it is | `feature_breakdown` (value/normalized/weight/contribution/source) + `rules_triggered` + `recommendations` in every response | `test_scorer.py::test_feature_provenance_in_breakdown`, `test_contributions_sum_to_score` |
| A5 | Domain rules complement the model (config-driven, hot-reload) | `return_risk/rules_engine.py` + `configs/return_risk_rules.yaml` (8 rules) | `tests/unit/return_risk/test_rules_engine.py` |
| A6 | Ground truth loop: record actual returns as labels for retraining | `POST /v1/return/update` + `/webhooks/razorpay/refund` → Redis `return_risk:labels` → nightly retrain path | `tests/integration/test_razorpay_webhooks.py` (label persistence), `tests/unit/test_ab_return_risk.py` |
| A7 | Honest model evidence, not aspirational numbers | ROC-AUC measured via `roc_auc_score`; ablation (LOFO) proves each feature; base generator git-guarded | `--full-verify` checks 1 (base-gen untouched), 10 (ablation baseline 0.8087), 7 (no hardcoded fallbacks) |

## B. Transaction fraud risk (live path)

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| B1 | Real-time velocity / geo / device signals | `POST /v1/score` → `engine/statistical_filter.py` (L1) on Redis `velocity:*`, `dfp:*`, `ud:*`, `benford:*` | `tests/unit/test_statistical_filter.py`, `tests/integration/test_score_path.py` |
| B2 | Graph / network intelligence (who else shares this device) | `engine/graph_loader.py` + `engine/graph_feature_engine.py` (L2 GNN), ensemble fusion in `engine/ensemble.py` | `tests/integration/test_graph_integration.py`, `tests/unit/test_ensemble.py` |
| B3 | A single auditable verdict with the rules that fired | Response includes `triggered_rules`, `layer_triggered`, explanation persisted for BLOCK/REVIEW | `tests/chaos/test_chaos_track2.py` (timeout/mock resilience), live check `suspicious burst → BLOCK` |

## C. Chargeback response (remedial path)

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| C1 | Assemble a rebuttal from evidence captured at transaction time | `POST /v1/chargeback/respond` → `chargeback/rebuttal_builder.py` + `evidence_collector.py` (read-only re-read of the audit chain) | `tests/unit/chargeback/test_rebuttal_builder.py`, `test_evidence_collector.py`, `tests/integration/test_chargeback_flow.py` |
| C2 | Deterministic response type + confidence + completeness | ACCEPT/REJECT/PARTIAL + completeness score + warnings | Live check `winnable → REJECT conf 1.0`, `weak → PARTIAL + 2 warnings` |
| C3 | Human-in-the-loop before anything goes out | Draft cached (30-day TTL); only `chargeback:admin` can submit via `POST /v1/chargeback/{id}/submit` | `tests/integration/test_chargeback_api.py` (RBAC), `configs/rbac.yaml` |
| C4 | Signed webhooks for dispute events, unverified payloads rejected | `/webhooks/razorpay/chargeback` + `chargeback/signatures.py` (constant-time HMAC) | `tests/unit/chargeback/test_signatures.py`, `test_webhook.py`; live check (bad sig → 400, good sig → 200) |

## D. Razorpay platform integration

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| D1 | Pre-ship hook for a merchant's `order.paid` | `/webhooks/razorpay/return-risk` (HMAC-verified) → `integrations/razorpay_adapter.py` (paise→₹, method→enum, notes→features) | `tests/integration/test_razorpay_webhooks.py`, `tests/unit/test_razorpay_adapter.py` |
| D2 | `refund.processed` becomes a training label | `/webhooks/razorpay/refund` → `return_risk:labels` | `test_razorpay_webhooks.py::test_refund_processed_records_label` |
| D3 | Order/payment/refund client for reconciliation & backfill | `integrations/razorpay_orders_client.py` (test-mode, HTTP Basic auth, mock-mode default) | `docs/RAZORPAY_INTEGRATION.md`; live keys verified against `api.razorpay.com/v1` |
| D4 | Dispute contest client (real or mock) | `chargeback/razorpay_client.py` (`GET /disputes/:id`, `PATCH /disputes/:id/contest`, evidence upload) | `tests/unit/chargeback/test_razorpay_client.py`, `tests/chaos/test_chaos_track2.py` |
| D5 | No secrets in the repo | Credentials only via env (`RAZORPAY_*`); `.env` git-ignored | `CONTRIBUTING.md` §secrets; `git ls-files` shows no `.env` |

## E. Governance, compliance & explainability

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| E1 | Tamper-evident, PII-masked audit trail of decisions | `store/audit_log.py` (hash-chained JSONL + PII masking) | `tests/unit/chargeback/test_audit_log_reader.py`, `tests/unit/test_security_hardening.py` |
| E2 | Role-based access control on sensitive surfaces | `api/rbac.py` + `configs/rbac.yaml` (`chargeback:admin`, `score:read`, …) | `tests/integration/test_security_api.py`; live check RBAC 403 paths |
| E3 | Encryption at rest for payment data | AES-256 (`ENCRYPTION_KEY` env), dev-only default with prod rotation note | `tests/unit/test_security_hardening.py`, `.env.example` |
| E4 | Decision explanations persisted for audits (RBI AI-1 / PCI 10.x) | `api/routes/score.py::_persist_explanation` for BLOCK/REVIEW | `tests/integration/test_api.py` (explanation artifacts) |
| E5 | Drift monitoring so model degradation is visible | `/admin/drift/return-risk` + PSI estimator (43.4 → 3.86 after fix) | `tests/unit/test_drift.py`, `test_drift_report.py`; live check `/admin/drift/return-risk → 200` |
| E6 | Regional compliance (data region, no cross-border replication by default) | `DATA_REGION=IN`, `CROSS_BORDER_REPLICATION=false` in env/config | `docs/COMPLIANCE_DELTA.md`, `configs/config.yaml` |

## F. Evidence integrity & reproducibility

| # | Requirement | Implementation | Evidence |
|---|---|---|---|
| F1 | All headline numbers reproduce from one command | `python scripts/run_all_scenarios.py --full-verify` → 10/10 PASS | `reports/full_verify_output.txt` (committed) |
| F2 | Byte-identical training (no unseeded RNG, no timestamps) | Determinism check: train × 3 twice, byte-compare result JSONs | `--full-verify` check 2 |
| F3 | Docs stay in lockstep with measured numbers | `docs/_number_manifest.json` + `scripts/verify_doc_consistency.py` | `--full-verify` check 8 |
| F4 | Live Docker stack passes its curated scenarios | `scripts/seed_demo_data.py` + `scripts/verify_live_stack.py` → 11/11 PASS | Live run (honest LOW 0.03, serial HIGH 0.98, burst BLOCK) |
| F5 | Cost model is derived from measured operating points, never hardcoded | `docs/cost_model/calculator.py` (no-fallback), `--full-verify` check 7 | `tests/unit/test_cost_model.py` (₹17.4L pinned) |
| F6 | Fixed, wheel-universal ML stack for cross-platform reproducibility | `requirements.txt` pins numpy/pandas/scipy/sklearn/xgboost for Python 3.11 (macOS + Linux) | `--full-verify` on a fresh clone reproduces byte-identical numbers |
| F7 | Feature-waterfall explainability — show *why* a score is what it is | `POST /v1/return/explain` (per-feature gain importance × value, neutral base 0.5) | `tests/integration/test_return_risk_api.py::TestReturnRiskExplain`; dashboard Model Waterfall section |
| F8 | Abuse-ring sentinel — coordinated-abuse detection, defense-only | `return_risk/feature_engine.py` address-hash tracking + `R-RULE-09` score-floor override (0.85) | `tests/unit/return_risk/test_scorer.py` (ring → HIGH; family co-shipping → no false positive); live demo seeds a 4-user ring |
| F9 | Temporal integrity — no look-ahead bias in DGP features or split | `scripts/verify_temporal_integrity.py` (chronology + split leakage + latent-sampled first-order features), wired as `--full-verify` check 11 | `--full-verify` → 11/11 PASS |

---

## Verified totals

- **Hermetic ML suite:** `--full-verify` → **11/11 PASS** (base-gen integrity, byte-identical determinism, AUC gates, ₹ gates, no-hardcoded-fallbacks, doc & dashboard consistency, ablation baseline, temporal integrity).
- **Live Docker stack:** `verify_live_stack.py` → **11/11 PASS**.
- **Test suite:** `pytest tests/` → **485 passed, 1 skipped** (47 test modules incl. chaos, security, graph, chargeback, return-risk, abuse-ring, explain).

## Honest gaps (documented, not hidden)

1. **Synthetic data.** Labels come from a calibrated DGP, not real merchant data.
2. **No live pilot yet.** The 0.50 gate and base-rate calibration are projections; an A/B test with a live merchant is the first next step.
3. **Model not yet trained on live-distributed features.** The demo path is aligned and verified 11/11, but the production scorer is still the offline-DGP-trained model (see README "What I'd Do Next" #1).
4. **Razorpay disputes live codec pending.** Schema tested against the real API surface; live dispute payloads not yet exercised (no disputes exist on the test account).

_Map: [`docs/TRACK2_ARCHITECTURE.md`](TRACK2_ARCHITECTURE.md) · Evidence: [`reports/full_verify_output.txt`](../reports/full_verify_output.txt) · Defense: [`docs/INTERVIEW_DEFENSE.md`](INTERVIEW_DEFENSE.md)_
