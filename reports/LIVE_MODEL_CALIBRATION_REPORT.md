# Calibration Gap Closure — Live-Model Report

**Date:** 2026-08-31 · **Decision:** Option B (ship the live-features model) · **Branch:** `master`

This report records exactly what was done to close the calibration gap — and
what has deliberately **not** been done. Every number below is measured, and
every claim is pinned by a check in `--full-verify` or the live stack.

---

## 1. The decision gate (measured, not guessed)

| Metric | Value | Gate |
|---|---|---|
| Live-features held-out test PR-AUC | **0.8139** | ≥ 0.7991 → **Option B**; < 0.79 → Option A |
| Live-features test ROC-AUC | **0.7965** | measured |
| Re-train determinism | **byte-identical** across two runs (sha256 match) | — |

The model is trained on the **exact 7-feature vector `ReturnRiskFeatureEngine`
computes** — Redis archetype profiles → the real feature engine → the model
schema — with feature-driven labels (the DGP's `_return_probability` applied to
live feature values + hidden confounders + noise) and the same per-user
chronological 60/20/20 split and XGBoost hyperparameters as the DGP trainer.
This is the honest fix: the live scorer now runs a model calibrated to the
features it actually computes (`device_fingerprint_match` = neutral 0.5,
`days_since_last_order` from `last_activity`, ratio clamped to `[0.15, 4.0]`).

## 2. What was done

| # | Item | Proof |
|---|---|---|
| 1 | `scripts/train_live_features.py` — live-pipeline training + decision gate | committed, `--full-verify` check 12 |
| 2 | Shipped `models/return_risk_xgb_live.json` as the production model | `return_risk/scorer.py` `DEFAULT_XGB_MODEL_PATHS` (live first) |
| 3 | `models/live_features_results.json` (metrics + operating curve) | committed |
| 4 | `--full-verify` **check 12**: live model re-trains byte-identical + PR-AUC ≥ 0.79 | `scripts/run_all_scenarios.py` |
| 5 | Live stack re-verified on the shipped model → **11/11** | `verify_live_stack.py` on Docker |
| 6 | Full suite → **12/12 ALL CHECKS PASS** | `reports/full_verify_output.txt` (regenerated) |
| 7 | 498 tests pass with the live model as primary | `pytest tests/` |
| 8 | Full re-anchor of every doc/score to the live model | sweep confirmed zero stale references |

**New measured live scores (seeded demo, shipped model):**

| Scenario | Score | Tier |
|---|---|---|
| Serial returner (`U_SERIAL_001`, COD) | **0.9712** | HIGH |
| Honest customer (`U_HONEST_001`, electronics) | **0.0589** | LOW |
| Abuse-ring `U_RING_001..003` | **0.0975** | LOW |
| Abuse-ring `U_RING_004` (shared pincode 560037) | **0.85** | HIGH (R-RULE-09 floor) |

## 3. Determinism re-verified on the new model

- `--full-verify` check 12 runs `train_live_features.py` twice and asserts
  `live_features_results.json` is **byte-identical** (verified: `f94647fb…` on
  both runs).
- The DGP determinism contract (checks 1–2, train × 3 twice byte-identical)
  is unchanged and still passes.
- This is the credibility signal the plan flagged — it is now pinned for the
  production model too, not just the evidence suite.

## 4. No stale numbers anywhere (verified by sweep)

A full-repo sweep for the old demo scores (`0.1157`, `0.9841`, `LOW 0.03`,
`HIGH 0.98`, `≈ 0.98`, `≈ 0.03`), old test counts (`495 passed`) and the old
banner text ("Stage 1 model on Stage 1-schema features") returned **zero
matches**. The only remaining "11/11" references are the **live stack** (11
checks), which is correct — the hermetic suite is 12/12.

## 5. What has NOT been done (honest, deliberate)

1. **Real merchant labels.** The model is now calibrated to the live feature
   *distribution*, but every label is still synthetic. The Phase-2 pilot in
   `docs/REAL_DATA_ROADMAP.md` — 1,000 real orders from one Razorpay merchant —
   is the next step: validate the 18% return rate, feature importances, and
   calibrate the cost model on observed numbers.
2. **A/B test of the 0.50 gate on live orders.** The champion/challenger
   harness (`ml/ab_testing.py`) is built but unexercised — needs live orders.
3. **Cost-model re-calibration on the live model.** The ₹ figures (₹17.4L →
   ₹53.5L) still come from the evaluated DGP operating curve (the data-maturity
   evidence story). The live model's own operating curve is committed in
   `models/live_features_results.json`; re-anchoring the cost model to it
   (or to real data) is part of the pilot.
4. **Vertical-specific gate tuning** — needs merchant data.
5. **Razorpay live disputes codec** — out-of-scope extension; schema tested,
   no live disputes exist on the test account.
6. **Neo4j / Ollama / production deployment** — out-of-scope for the
   return-risk track; the app degrades gracefully without them.

## 6. The interviewer answer (sharp, no deflection)

> "The live scorer now runs a model **trained on the exact feature vector the
> live API computes** (`models/return_risk_xgb_live.json`, test PR-AUC 0.8139,
> `scripts/train_live_features.py`). The old 0.50-on-per-order-labels figure
> was about a *different generator* whose labels were pure noise. The
> distribution gap is closed — the remaining calibration is real merchant
> labels, which is exactly what the Phase-2 pilot is for. You can verify the
> whole thing with `make verify` (12/12, including a determinism re-train of
> the shipped model) and `make verify-live` (11/11)."

---

_Committed: `913cf3e` (model + trainer), `9f278eb` (verify check 12), `4d84a54` (full re-anchor). All on `origin/master`._
