# Calibration Gap — Honest Accounting

## TL;DR

The production XGBoost model is **trained on the offline DGP** (7 synthetic
features) while the live API **scores Redis-enriched features**. This
model-pipeline mismatch caused **two live-verification failures**. Both were
fixed by aligning the *live feature pipeline* to the model's training envelope
(not by hardcoding demo overrides, and not by retraining the model). The
**remaining** gap — the model is still not *trained* on live-distributed
features — is documented below and tracked as the first "What I'd Do Next".

**Current status:** `scripts/verify_live_stack.py` passes **11/11** on the
rebuilt Docker stack. There are no known live failures today.

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
  not order value. Demo profiles carry realistic `avg_order_value` /
  `last_activity` so the serial returner's ratio stays ~1.0 (HIGH 0.98) while
  the honest customer uses the neutral fallback (ratio 0.16 → LOW 0.03).
  Regression tests pin both tiers and assert the ratio stays in-envelope.

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

## The remaining gap (honest, not hidden)

The two failures above were **feature-pipeline alignment** bugs. The deeper
mismatch the plan called out is still real:

- The production scorer loads `models/return_risk_xgb_v1.json`, trained on the
  offline DGP's 7 features.
- The live API feeds it features computed by `ReturnRiskFeatureEngine` from
  Redis (user rates, merchant baselines, computed txn features) plus a neutral
  `device_fingerprint_match = 0.5` and a `days_since_last_order` default of 60.
- These distributions are now **inside the model's training envelope** for the
  curated demo scenarios (verified 11/11), but the model has **not been
  retrained on live-distributed feature data**. A real merchant's Redis
  profiles could still push features outside the envelope.

**Why we didn't retrain the model now:** retraining changes every benchmarked
number and would invalidate the pinned `--full-verify` evidence. The honest
sequence is: keep the offline model as the auditable baseline, and **recalibrate
on real (or live-shaped) merchant data** — the documented first next step
(README → "What I'd Do Next" #1). The API already logs the feature vector for
every scored order (`xgb_features`), so the calibration dataset is being
collected.

---

## Guardrails (so this never silently regresses)

1. `tests/unit/return_risk/test_scorer.py` pins honest → LOW (ratio ≤ 4.0) and
   serial → HIGH.
2. `verify_live_stack.py` asserts the tiers end-to-end against a real Redis.
3. `--full-verify` determinism + doc-consistency checks keep the numbers and
   the narrative in lockstep.
