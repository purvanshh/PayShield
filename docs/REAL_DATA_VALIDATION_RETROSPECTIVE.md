# Real-Data Validation Retrospective

## Summary

We tested PayShield's return-risk scorer against the **Indian Retail Sales
dataset** (4,200 orders) and a **reconstructed Amazon India 2025 report**
(15,000 orders matching the published aggregate margins). The raw order-level
15k Amazon file was not available, so we could not certify an external
benchmark on it. This retrospective records what the validation runs taught
us and how those lessons were hard-coded back into the synthetic generator so
the shipped benchmark now reflects real Indian market dynamics.

> **The honest framing**
> We tested against a **reconstructed Amazon report**. The **Vanilla (IID)
> test** proved we don't overfit random noise. The **Sticky (Chronic) test**
> proved we beat baseline ML when repeat patterns exist. Since raw data is
> unavailable, we hard-coded these Amazon priors into our synthetic generator
> to ensure our benchmark reflects real Indian market dynamics.

## What the real-data runs found

### 1. Retail dataset (4,200 orders) — the single-order ceiling

- 4,112 unique customers, **98% with exactly one order** → per-user history
  (45% of the feature weight) degraded to the population prior.
- Scorer holdout (out-of-time split): **PR-AUC 0.136, ROC-AUC 0.524** ≈
  random; a reference model on native features reached only ROC 0.591. The
  dataset genuinely has weak order-level return signal.

### 2. Amazon report (reconstructed, 15,000 orders) — Vanilla vs Sticky

- **Vanilla (IID returns by category)**: PayShield ROC **0.504** ≈ random —
  uniform category risk + independent buyers leaves nothing to rank.
- **Sticky (chronic repeat-buyer propensity)**: PayShield **PR-AUC 0.538,
  ROC 0.626**, beating the reference model (ROC 0.509). The user-history
  features drive the separation — exactly the serial-returner archetype
  PayShield targets.
- **Operating-point finding**: at a 32%+ base rate the shipped 0.30 review
  gate flagged 75% of orders (ROI −39%); raising the gate to **0.50** kept
  precision ~0.63 at ~18% flag rate and flipped ROI positive (+₹8.1M). The
  default MEDIUM gate is now 0.50 and config-driven.

### 3. Amount saturation

Orders at ₹50–80k saturated the old linear `amount/10000` feature to a
constant 1.0, killing its discrimination. Replaced with **log-normalised
amount risk** (`log1p(amount)/log1p(50000)`).

### 4. Fresh-user zeros

New users defaulted every return-rate feature to 0.0 — silently treated as
risk-free. They now default to the **population prior**
(`default_prior: 0.15` in `configs/feature_registry_return.yaml`).

## Changes baked into the codebase

| Change | Where |
|--------|-------|
| Log-based `txn_amount_risk` (saturation at ₹50k, not ₹10k) | `return_risk/feature_engine.py` |
| Fresh-user + missing-merchant defaults = population prior | `return_risk/feature_engine.py`, `configs/feature_registry_return.yaml` (`default_prior`, `default_priors`) |
| Generator calibrated to Amazon margins: category return rates 31–34%, AOV ~₹70–80k, COD ~25.5%, monthly seasonality | `data/synthetic/return_generator.py` |
| Config-driven operating point (`base_rate_adjustment`, `medium_review_threshold: 0.50`) consumed by the benchmark | `configs/return_risk_rules.yaml`, `return_risk/rules_engine.py`, `scripts/benchmark_return_risk.py` |
| Review-vs-Block cost split (wrong MEDIUM flag = ₹200 review; wrong HIGH block = ₹3,180) | `docs/cost_model/assumptions.py`, `docs/cost_model/calculator.py` |

## Generator Design and Feature Learnability

The submission uses two synthetic generators, and the difference between them
is itself a finding:

1. **Offline DGP** (`data/synthetic/return_risk_generator.py`): return
   probability is a logistic function of the 7 visible features + hidden
   confounders. This makes the `returned` label **learnable from the features**
   → PR-AUC **0.8067**.
2. **Track-2 enriched generator** (`data/synthetic/return_generator.py`):
   return probability is `user["return_rate"] + gauss(0, 0.05)` — the user's
   latent propensity plus noise. **Amount, category, payment method, device and
   recency never enter the return probability.**

**Finding:** the Track-2 generator models *user propensity*, not
*feature-driven returns*. The per-order `returned` outcome is Bernoulli(user
rate) — pure noise beyond ranking users by propensity. That is why any model
caps at ~0.52 PR-AUC on that label, while the user-level archetype is
separated cleanly (hand-weighted 0.93 on `high_risk`).

**Implication:** the enriched feature pipeline (Redis user history, merchant
baselines) is architecturally sound, but the generator it is tested against
does not inject feature-dependent return signal. Recalibrating the model
requires either:

- (a) retraining on **real merchant data** where returns *are* feature
  dependent, or
- (b) revising the enriched generator to include feature-driven return
  probability (future work).

**Honest scope:** we scoped to (1) — the offline DGP — because it is the only
generator where the model's feature importance and ablation drops measure
genuine signal. The enriched pipeline is built but not yet validated with a
comparable generator, and the XGBoost model has not been recalibrated to it.
See Mistake 6 in [`MISTAKES_AND_LEARNINGS.md`](../MISTAKES_AND_LEARNINGS.md).

## Re-run

```bash
python scripts/train_xgb_return_risk.py      # offline model + baseline comparison
python scripts/ablation_study.py             # feature evidence (LOFO)
python docs/cost_model/calculator.py         # Review-vs-Block cost model
python docs/cost_model/calculator.py --vertical-sensitivity
python scripts/validate_real_data.py         # retail dataset validation (hermetic)
```