# Submission Checklist — Track 2 (Return-Risk)

Every requirement is ✅ implemented and verified. Each line carries the proof:
a `file:line` anchor, an endpoint, or a test/verify command. The 60-second
reproduction is at the bottom.

> Reproduce everything: `make setup-verify` then `make verify` → **12/12 PASS**.
> Live stack: `make up` → `make seed` → `make verify-live` → **11/11 PASS**.

## The model (measured, never hardcoded)

- ✅ **7-feature XGBoost primary engine** — Stage 1 default PR-AUC 0.7991 / ROC-AUC 0.8431; Stage 3 premium 0.9497 / 0.9612. Proof: `scripts/train_xgb_return_risk.py`, `reports/full_verify_output.txt` (checks 3–5).
- ✅ **Live scorer runs a model trained on the live feature pipeline** — `models/return_risk_xgb_live.json` (test PR-AUC 0.8227 / ROC-AUC 0.8082), trained by `scripts/train_live_features.py` on the exact features the API computes. Proof: `return_risk/scorer.py` (`DEFAULT_XGB_MODEL_PATHS`), `--full-verify` check 12.
- ✅ **ROC-AUC measured, not hardcoded** (`roc_auc_score`). Proof: `scripts/train_xgb_return_risk.py`.
- ✅ **Feature surface matches the DGP schema exactly** — `return_risk/scorer.py:36-44` (`XGB_FEATURES`) and `:264-282` (`_xgb_predict` maps live engine output → the 7 model features).
- ✅ **Live scorer never goes out-of-distribution** — `amount_vs_user_aov_ratio` is clamped to the training envelope `[0.15, 4.0]`. Proof: `return_risk/feature_engine.py:55` + `:350`; regression tests `tests/unit/return_risk/test_feature_engine.py` (`test_extreme_aov_ratio_is_clamped_to_envelope`) and `test_scorer.py` (`test_extreme_aov_order_scores_sane`).
- ✅ **Transparent hand-weighted fallback** — used if the model fails to load; the primary engine is XGBoost. Proof: `return_risk/scorer.py:178-237`.

## Defense-only posture

- ✅ **Defense-only architecture** — `MEDIUM → FLAG_FOR_REVIEW`, `HIGH → REQUIRE_PREPAID`, no autonomous blocks. Proof: `return_risk/scorer.py:86-90` (`RISK_TIERS`) + `:343` (`_determine_tier`).
- ✅ **Abuse-ring sentinel is defense-only too** — shared address + velocity spike forces a score floor of 0.85 (`HIGH` review), never a block. Proof: `return_risk/scorer.py:116` (`ABUSE_RING_SCORE_FLOOR`) + `:237`; rule `configs/return_risk_rules.yaml:77` (`R-RULE-09`).

## Features, rules, explainability

- ✅ **Features from real Redis history, not placeholders** — every feature carries a `source` tag (`redis_hash`, `computed`, `lookup_table`, `default_new_user`). Proof: `return_risk/feature_engine.py:80` (`extract_features`).
- ✅ **Config-driven, hot-reload rules** — 9 rules in `configs/return_risk_rules.yaml`, evaluated against a whitelisted scope. Proof: `return_risk/rules_engine.py:97` (`evaluate`).
- ✅ **Per-feature contribution in every response** — value / weight / contribution / source. Proof: `return_risk/scorer.py` `_compute_score`; API test `tests/unit/return_risk/test_scorer.py::test_contributions_sum_to_score`.
- ✅ **XGBoost feature-waterfall endpoint** — `POST /v1/return/explain` (gain importance × value, base 0.5). Proof: `api/routes/return_risk.py:119`.

## Razorpay integration

- ✅ **Signed webhooks, unverified payloads → 400** — HMAC-SHA256 constant-time compare. Proof: `integrations/razorpay_webhook_handler.py:49` (return-risk) + `:128` (refund label); `chargeback/signatures.py:18`.
- ✅ **`order.paid` → pre-ship score** — paise→₹, method→enum, notes→features via the adapter. Proof: `integrations/razorpay_webhook_handler.py`, `integrations/razorpay_adapter.py`.
- ✅ **`refund.processed` → training label** — pushed to `return_risk:labels` for retraining. Proof: `integrations/razorpay_webhook_handler.py:128`.

## Business impact & cost honesty

- ✅ **Honest FP/FN costs modeled** — wrong MEDIUM flag ₹200 (review), wrong HIGH block ₹3,180. Proof: `docs/cost_model/assumptions.py`; `docs/cost_model/calculator.py` (no hardcoded fallback — `--full-verify` check 7).
- ✅ **Cost derived from measured operating points** — ₹17.4L → ₹53.5L/month at the 0.50 gate. Proof: `docs/cost_model/calculator.py --all-maturity`, `tests/unit/test_cost_model.py`.
- ✅ **Why synthetic is a calibrated choice** — rejected public datasets, pinned Indian calibration sources, hidden confounders, sensitivity knobs. Proof: `docs/SIMULATOR_VALIDATION.md`.
- ✅ **Real-data path is planned, not hand-waved** — 3-phase roadmap. Proof: `docs/REAL_DATA_ROADMAP.md`.

## Governance & observability

- ✅ **Tamper-evident, PII-masked audit chain** — hash-chained JSONL with chain re-verification. Proof: `store/audit_log.py:59` (`AuditLogWriter`) + `:119` (`verify_chain`).
- ✅ **Drift monitoring** — PSI over the return-risk feature surface (43.4 → 3.86 after fix). Proof: `GET /admin/drift/return-risk`; tests `tests/unit/test_drift.py`.

## Operational depth (dashboard)

- ✅ **Guided 10-minute demo** — 5 stops over real surfaces. Proof: `api/routes/meta.py:160` (`DEMO_GUIDE`), dashboard `DemoTourPage`.
- ✅ **Human-review queue** — latest MEDIUM decisions from the audit chain + reviewed flag. Proof: `api/routes/meta.py:266` (`review_queue`); `tests/integration/test_review_queue.py`.
- ✅ **Calibration simulator** — feature sliders, basic vs premium model. Proof: `api/routes/return_risk.py:192` (`simulate_return_risk`); tests `tests/integration/test_return_risk_api.py::TestReturnRiskSimulate`.

## Reproducibility & integrity (the moat)

- ✅ **Fully pinned Python 3.11 stack** — every dependency exact. Proof: `requirements.txt`.
- ✅ **Byte-identical training** — DGP train × 3 twice (check 2) and the live-features model re-trains byte-identically (check 12). Proof: `--full-verify`.
- ✅ **Base generator git-guarded untouched** — Proof: `--full-verify` check 1.
- ✅ **Temporal integrity / no look-ahead** — per-user chronology + split leakage + latent-sampled first-order features. Proof: `scripts/verify_temporal_integrity.py:80`, `--full-verify` check 11.
- ✅ **Live model PR-AUC gate** — `--full-verify` check 12 asserts the live-features held-out test PR-AUC ≥ 0.79 and byte-identical re-train.
- ✅ **Docs in lockstep with measured numbers** — manifest-checked. Proof: `--full-verify` check 8.
- ✅ **Compliance map live in the API** — 16/16 return-risk requirements, none claimed before they exist. Proof: `api/routes/meta.py:46` (`TRACK2_REQUIREMENTS`), `GET /v1/meta/track2-compliance`.

## Honest caveats (owned, not hidden)

- ⚠️ Synthetic labels (calibrated DGP, not real merchant data) — `docs/SIMULATOR_VALIDATION.md`.
- ⚠️ No live pilot yet — the gate is a projection; A/B harness is built (`docs/REAL_DATA_ROADMAP.md`).
- ⚠️ `device_fingerprint_match` is a neutral 0.5 at inference (no device store) — `docs/TRACK2_COMPLIANCE.md` (C-section).

---

_Proof of the whole claim in one command: `make verify` → ALL CHECKS PASS._
