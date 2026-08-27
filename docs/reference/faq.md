# Frequently Asked Questions

## What is PayShield?

PayShield is a student **Proof-of-Concept return-risk scorer** for Indian
e-commerce merchants, built on Razorpay's infrastructure. It scores an order
*before it ships* and predicts whether it is likely to be returned. It is **not
production software** — see the README's honest prototype note.

## How does return-risk scoring work?

Seven features (recent return rate, order value vs AOV, category baseline,
payment-method risk, device match, recency) feed an **XGBoost model** (primary)
with a transparent hand-weighted composite as the automatic fallback. The score
maps to a tier: LOW → ship, MEDIUM → review, HIGH → require prepaid. Every score
carries a per-feature value, weight, contribution and source tag.

## Why are there three PR-AUC numbers?

PayShield is evaluated across **three merchant-maturity scenarios** with
identical model architecture — only the data source changes:

| Stage | PR-AUC | ROC-AUC | ₹/month (Electronics) |
|---|---|---|---|
| Stage 1: Basic (floor) | 0.8042 | 0.8448 | ₹36.2L |
| Stage 2: Enriched | 0.8881 | 0.9217 | ₹45.0L |
| Stage 3: Premium | 0.9467 | 0.9593 | ₹53.6L |

Stage 1 is the honest floor (7 features, high hidden variance). Stage 3 is a
premium merchant with mature instrumentation (9 features, low noise). The
Redis-enriched feature pipeline exists in the codebase but the XGBoost model
has **not yet been recalibrated to real merchant data** — that is the honest
next step. See [`MISTAKES_AND_LEARNINGS.md`](../../MISTAKES_AND_LEARNINGS.md)
(Mistake 7) for why three scenarios instead of a silent overwrite, and
Mistake 6 for how the earlier 0.9311 archetype metric was removed.

## Is the data synthetic?

Yes. Labels come from a generator calibrated to published Indian e-commerce
distributions, with **hidden confounders** (product rating, delivery speed,
packaging, weather delays, customer mood) the model never observes. That makes
the model learn from noisy, incomplete signal — like real data — and the honest
PR-AUC is lower than a circular benchmark would produce.

## What does the cost model say?

A 10k-order fashion merchant saves **₹17.0 lakh/month** at the 0.50 review gate
(Stage 1 XGBoost operating point: precision 0.635, recall 0.811). A wrong MEDIUM
flag costs ₹200 of operator time (order still ships); a wrong HIGH block costs
₹3,180. The measured gate sweep shows 0.50 is optimal for high-return
verticals. The three-scenario maturity table shows savings scaling to ₹53.6L
for a premium electronics merchant. See [`docs/COST_MODEL.md`](../COST_MODEL.md)
including where the gate breaks (vertical sensitivity).

## How do I reproduce the numbers?

Hermetic, no services needed:

```bash
python scripts/train_xgb_return_risk.py
python scripts/ablation_study.py
python scripts/tune_xgb.py
python docs/cost_model/calculator.py --vertical-sensitivity
```

## What are the honest limitations?

1. Synthetic data (no real merchant pilot yet).
2. `device_fingerprint_match` is a neutral 0.5 at inference (no return-risk
   device store).
3. Compliance certifications are out of scope for a PoC.

## How is data privacy handled?

PII is masked at write in the tamper-evident audit log (`store/audit_log.py`),
and the audit chain is hash-chained for verifiability.

## How do I contribute?

See [CONTRIBUTING.md](../../CONTRIBUTING.md). The return-risk surface is
`return_risk/`, `api/routes/return_risk.py`, and the evidence scripts in
`scripts/`.