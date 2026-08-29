# Business Impact

## Headline Metric

**PayShield saves a fashion merchant ₹17.4 lakh per month on 10,000 orders**
(Stage 1: Basic floor) by preventing high-risk returns before they ship — and a
**premium electronics merchant ₹53.5 lakh per month** at Stage 3.

> Reproduce it: `python docs/cost_model/calculator.py --all-maturity` (hermetic).

## Progressive Merchant Maturity

PayShield is evaluated across three named merchant-maturity stages. Each is a
different merchant segment with a documented data-generating process; the model
architecture, split and evaluation protocol are **identical** across stages —
only the data source (observed features + unobserved-variance budget) changes.
Stage 1 is the honest floor; Stage 3 is a premium merchant with mature data
instrumentation (product ratings + delivery SLAs observed, low hidden variance,
low label noise).

| Stage | PR-AUC | ROC-AUC | ₹/month (Fashion) | ₹/month (Electronics) | ROI (Electronics) |
|---|---|---|---|---|---|
| **Stage 1: Basic** | 0.7991 | 0.8431 | ₹17.4L | ₹36.8L | 36.0% |
| **Stage 2: Enriched** | 0.8834 | 0.9198 | ₹21.4L | ₹44.7L | 43.7% |
| **Stage 3: Premium** | 0.9497 | 0.9612 | ₹26.0L | **₹53.5L** | 52.4% |

> AUCs are the default-XGBoost model (one file per row, no tuned-vs-default
> mixing); the tuned champions reach 0.8089 / 0.8875 / 0.9488 PR-AUC
> (`reports/scenario_comparison.md`).

The ₹ figures rise because the **measured** precision/recall at the 0.50 review
gate improve with data maturity — not because the base rate or AOV changed. The
saving scales with data quality: the same scorer, applied to a merchant that
observes more return drivers and measures them more cleanly, prevents more
returns at higher precision. The Stage 1 ₹17.4L fashion figure remains the
conservative floor a panelist can take to any merchant.

## The Math (10,000 fashion orders/month, ₹2.5k AOV, 18% return rate, Stage 1)

| Scenario | Monthly Cost | Savings vs. Baseline |
|----------|-------------|----------------------|
| Baseline (no scorer) | ₹50.31L | — |
| With PayShield MEDIUM+ gate (0.50) | ₹32.93L | **₹17.4L saved** |
| Annual savings | — | **₹2.09 cr** |
| Net savings per 1,000 orders | — | **₹1.74L** |

Flags 1,461 of 1,800 expected returns; prevents ~659 returns/month (diversion
effectiveness 70%); ROI **+34.5%**. Operating point: precision **0.644**,
recall **0.812** — the Stage 1 XGBoost model measured on the held-out test set
(`models/return_risk_results_basic.json`).

## Cost Asymmetry (Why This Works)

| Error Type | Cost | Action |
|-----------|------|--------|
| False MEDIUM flag (review) | ₹200 | Order still ships, operator checks |
| False HIGH block (prepaid gate) | ₹3,180 | Lost order + CAC + churn risk |

Because review is ~16× cheaper than blocking, the gate optimizes for
**precision at the review tier** — catch the clearly-high tail without
sacrificing good orders. Threshold selection is a cost optimization, not an
accuracy contest.

## ROI by Vertical (Stage 1 XGBoost operating point, gate 0.50, 10,000 orders/month)

| Vertical | Return Rate | Optimal Gate | Monthly Savings | ROI |
|----------|-------------|--------------|-----------------|-----|
| Fashion (high return) | 18% | 0.50 | **₹17.4L** | +34.5% |
| Electronics (low volume, high AOV) | 12% | 0.50 | **₹36.8L** | +36.0% |
| Grocery (very low, small AOV) | 4% | 0.50 | **₹2.4L** | +33.2% |

The gate is config-driven per merchant vertical (`configs/return_risk_rules.yaml`
→ `operating_point.medium_review_threshold`). The vertical-sensitivity sweep in
`docs/COST_MODEL.md` shows the optimal gate drifts up (0.60–0.70) as the base
return rate falls — 0.50 is right for high-return verticals.

> **Honest scope:** the cost model uses the **Stage 1 XGBoost** operating point
> (P 0.644, R 0.812 @ 0.50, measured in `models/return_risk_results_basic.json`).
> The Stage 2/3 maturity scenarios show how savings scale with data quality; the
> Redis-enriched feature pipeline exists in the codebase but the XGBoost model
> has **not** been recalibrated to real merchant data — that is the first
> "What I'd Do Next" item.

## How PayShield Differs from Typical Buildathon Submissions

| Dimension | Typical Submission | PayShield |
|-----------|-------------------|-----------|
| Model | Single XGBoost/LightGBM on a canned CSV | XGBoost primary + transparent hand-weighted fallback + rules engine |
| Evaluation | Accuracy on synthetic data | Cost model in ₹, naive baseline comparison, LOFO ablation, non-circular DGP |
| Infrastructure | Jupyter notebook | Docker, Redis, live webhooks, drift monitoring |
| Explainability | SHAP plots | Per-feature contribution in the API response, `engine` attribution, feature importance |
| Failure mode | Crashes or silent errors | Graceful degradation to defaults with explicit `source` tags, hand-weighted fallback |
| Honesty | README only | Evaluator guide, mistakes-and-learnings ledger, bug register |

The complexity is **intentional depth** — every layer maps to a merchant-visible
behavior or a measured number — not accidental bloat.

## What We'd Need to Validate

Real merchant A/B test. The harness is built (`ml/ab_testing.py`, the Razorpay
webhook integration, the live-stack verification script). We need live orders
to validate the 0.50 gate on real Indian return distributions — and to retrain
the XGBoost model on enriched feature distributions — that is the first item on
"What I'd Do Next."