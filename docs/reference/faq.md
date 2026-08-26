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

## Why are there two PR-AUC numbers?

| Pipeline | PR-AUC | What it measures |
|---|---|---|
| Offline XGBoost | 0.8067 | Raw 7 features + hidden-DGP noise (architecture validation) |
| Live Redis-backed | 0.9311 | Features enriched with real user history/baselines (production path) |

The **+0.12 gap is feature engineering, not model choice** — enriching the same
features with real history matters more than algorithm tuning. We don't yet know
XGBoost-on-enriched PR-AUC; the A/B harness to measure it is built but needs a
live merchant.

## Is the data synthetic?

Yes. Labels come from a generator calibrated to published Indian e-commerce
distributions, with **hidden confounders** (product rating, delivery speed,
packaging, weather delays, customer mood) the model never observes. That makes
the model learn from noisy, incomplete signal — like real data — and the honest
PR-AUC is lower than a circular benchmark would produce.

## What does the cost model say?

A 10k-order fashion merchant saves **₹20.9 lakh/month** at the 0.50 review gate
(live enriched path). A wrong MEDIUM flag costs ₹200 of operator time (order
still ships); a wrong HIGH block costs ₹3,180. The 0.30 gate flags 75% of orders
and *loses* money; 0.50 flags 18% and saves. See [`docs/COST_MODEL.md`](../COST_MODEL.md)
including where the 0.50 gate breaks (vertical sensitivity).

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