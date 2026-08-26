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

## Why is there one PR-AUC number?

The evaluated number is the **offline XGBoost model, PR-AUC 0.8067** on the
`returned` label — trained on a non-circular DGP, validated on a per-user
chronological hold-out. The Redis-enriched feature pipeline exists in the
codebase and the live scorer runs on it, but the XGBoost model has **not yet
been recalibrated to enriched feature distributions**, so there is no comparable
enriched model number to report — that is the honest next step, not a headline.
See [`MISTAKES_AND_LEARNINGS.md`](../../MISTAKES_AND_LEARNINGS.md) (Mistake 6)
for how the earlier 0.9311 archetype metric was removed.

## Is the data synthetic?

Yes. Labels come from a generator calibrated to published Indian e-commerce
distributions, with **hidden confounders** (product rating, delivery speed,
packaging, weather delays, customer mood) the model never observes. That makes
the model learn from noisy, incomplete signal — like real data — and the honest
PR-AUC is lower than a circular benchmark would produce.

## What does the cost model say?

A 10k-order fashion merchant saves **₹17.5 lakh/month** at the 0.50 review gate
(offline XGBoost operating point: precision 0.677, recall 0.774). A wrong MEDIUM
flag costs ₹200 of operator time (order still ships); a wrong HIGH block costs
₹3,180. The measured gate sweep shows 0.50 is optimal for high-return
verticals. See [`docs/COST_MODEL.md`](../COST_MODEL.md) including where the gate
breaks (vertical sensitivity).

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