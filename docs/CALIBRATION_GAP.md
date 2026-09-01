# Calibration Gap — Honest Accounting

## TL;DR

The production XGBoost model is **trained on the offline DGP** (7 synthetic
features) while the live API **scores Redis-enriched features**. This
model-pipeline mismatch caused **two live-verification failures**. Both were
fixed by aligning the *live feature pipeline* to the model's training envelope
(commit `4207ff6`), and the deeper distribution gap is now **closed**: the
production scorer ships a model **trained on the exact feature vector the live
API computes** (`scripts/train_live_features.py`, test PR-AUC 0.8227). The
remaining honest step is **real merchant labels** (the pilot in
`docs/REAL_DATA_ROADMAP.md`).

**Current status:** the live scorer runs `models/return_risk_xgb_live.json`
(engine: xgboost, `model_path` in every response); `verify_live_stack.py`
passes **11/11**; the live-features training is a `--full-verify` check
(deterministic re-train + PR-AUC ≥ 0.82).

---

## The two historical failures (why they happened)

### Failure 1 — Honest customer → MEDIUM/HIGH (expected LOW)

- **Symptom:** `POST /v1/return/score` for the honest profile returned
  `0.58–0.80` (MEDIUM/HIGH) instead of LOW.
- **Root cause:** `return_risk/feature_engine.py` fell back to
  `avg_return_value` as the user's **average order value**. A ₹12,000
  electronics order on a profile with ₹1,500 of *returned* items produced
  `amount_vs_user_aov_ratio = 8.0` — **past the model's training ceiling of
  4.0** (the DGP clamps the ratio to `[0.15, 4.0]` and uses `log(ratio)` in its
  logit). Feeding an 8.0 ratio to a model that only ever saw ratios ≤ 4.0
  spiked the risk output. (A secondary contributor: `days_since_last_order`
  defaulted to 60, near the model's tail.)
- **Fix (commit `4207ff6`):** the feature engine now falls back to the
  **population AOV** (`₹74.5k`) instead of `avg_return_value` — return value is
  not order value. `amount_vs_user_aov_ratio` is clamped to the training
  envelope `[0.15, 4.0]`. Demo profiles carry realistic `avg_order_value` /
  `last_activity`. Regression tests pin both tiers and assert the ratio stays
  in-envelope.

### Failure 2 — Suspicious burst → ALLOW (expected BLOCK)

- **Symptom:** `/v1/score` for the seeded suspicious user returned ALLOW.
- **Root cause:** the burst verdict comes from **velocity rules** over Redis
  (`velocity:user:*`, `velocity:dev:*`, `velocity:loc:*`). When
  `scripts/seed_demo_data.py` had **not** been run (or Redis was flushed), the
  velocity lists were empty → no `V-RULE` / `G-RULE` fired → ALLOW. This is a
  **documented prerequisite** (seed, then verify), not a code defect.
- **Fix:** none needed in code. With the seeded velocity history the live check
  returns `BLOCK 1.0` (`V-RULE-02/03, G-RULE-01/02`). The seeder resets the
  demo velocity surfaces on every run so re-scoring is deterministic.

---

## The gap is now closed (Option B — train on live features)

The two failures above were **feature-pipeline alignment** bugs. The deeper
mismatch the plan called out — *the model isn't trained on the features the
live API computes* — is fixed:

- **`scripts/train_live_features.py`** trains XGBoost on the **exact 7-feature
  vector `ReturnRiskFeatureEngine` produces** (Redis profiles → feature engine
  → the model's schema), with feature-driven labels (the DGP's
  `_return_probability` applied to the live feature values + hidden confounders
  + noise). The split and training protocol are identical to the DGP trainer
  (per-user chronological 60/20/20).
- **Held-out test PR-AUC: 0.8227 / ROC-AUC: 0.8082** — above the DGP model's
  0.7991 floor, because the model is calibrated to the live distribution (where
  `device_fingerprint_match` is the neutral 0.5, `days_since_last_order` comes
  from `last_activity`, and the ratio is clamped). Trained with
  `scale_pos_weight=1.0` — the live distribution is near-balanced (~49% base
  rate), unlike the minority-positive DGP.
- The scorer now loads **`models/return_risk_xgb_live.json`** first
  (`DEFAULT_XGB_MODEL_PATHS`), so the live demo runs the calibrated model —
  serial returner **HIGH 0.94**, honest customer **LOW 0.03**, abuse-ring
  sentinel **HIGH 0.85** (score floor), verified 11/11.
- `--full-verify` gained a **check 12**: the live-features training must re-run
  **byte-identical** (determinism on the new model) and meet **PR-AUC ≥ 0.82**.

**What remains is real labels, not features.** The model is now calibrated to
the live feature *distribution*; the final calibration step is the Phase-2
pilot in `docs/REAL_DATA_ROADMAP.md` — 1,000 real orders to validate the
assumptions and calibrate the cost model, then A/B the gate. The API already
logs `xgb_features` for every scored order, so the calibration dataset is
being collected.

---

## Guardrails (so this never silently regresses)

1. `tests/unit/return_risk/test_scorer.py` pins honest → LOW (ratio ≤ 4.0) and
   serial → HIGH.
2. `verify_live_stack.py` asserts the tiers end-to-end against a real Redis.
3. `--full-verify` (12 checks) re-trains the live model deterministically, keeps
   the DGP evidence in lockstep with the manifest, and checks temporal
   integrity + doc consistency.

