# Business Impact

## Headline Metric

**PayShield saves a fashion merchant ₹20.9 lakh per month on 10,000 orders**
by preventing high-risk returns before they ship.

> Reproduce it: `python docs/cost_model/calculator.py` (hermetic).

## The Math (10,000 fashion orders/month, ₹2.5k AOV, 18% return rate)

| Scenario | Monthly Cost | Savings vs. Baseline |
|----------|-------------|----------------------|
| Baseline (no scorer) | ₹50.31L | — |
| With PayShield MEDIUM+ gate (0.50) | ₹29.38L | **₹20.93L saved** |
| Annual savings | — | **₹25.1L** |
| Net savings per 1,000 orders | — | **₹2.09L** |

Flags 1,089 of 1,800 expected returns; prevents ~750 returns/month (diversion
effectiveness 70%); ROI **+41.6%**.

## Cost Asymmetry (Why This Works)

| Error Type | Cost | Action |
|-----------|------|--------|
| False MEDIUM flag (review) | ₹200 | Order still ships, operator checks |
| False HIGH block (prepaid gate) | ₹3,180 | Lost order + CAC + churn risk |

Because review is ~16× cheaper than blocking, the gate optimizes for
**precision at the review tier** — catch the clearly-high tail without
sacrificing good orders. Threshold selection is a cost optimization, not an
accuracy contest.

## ROI by Vertical (10,000 orders/month, live enriched operating point)

| Vertical | Return Rate | Optimal Gate | Monthly Savings | ROI |
|----------|-------------|--------------|-----------------|-----|
| Fashion (high return) | 18% | 0.50 | **₹20.9L** | +41.6% |
| Electronics (low volume, high AOV) | 12% | 0.50 | **₹42.6L** | +41.6% |
| Grocery (very low, small AOV) | 4% | 0.30 | **₹1.5L** | +38.5% |

The gate is config-driven per merchant vertical (`configs/return_risk_rules.yaml`
→ `operating_point.medium_review_threshold`).

> **Honest framing:** these are the *live Redis-enriched* operating points
> (precision 0.984 @ 0.50). The offline XGBoost model on raw features alone
> saves **₹17.5L/month** (precision 0.677 @ 0.50) — the ₹3.4L difference is
> feature enrichment, not model choice. See the README's two-pipeline table.

## How PayShield Differs from Typical Buildathon Submissions

| Dimension | Typical Submission | PayShield |
|-----------|-------------------|-----------|
| Model | Single XGBoost/LightGBM on a canned CSV | XGBoost primary + transparent hand-weighted fallback + rules engine |
| Evaluation | Accuracy on synthetic data | Cost model in ₹, naive baseline comparison, LOFO ablation, non-circular DGP |
| Infrastructure | Jupyter notebook | Docker, Redis, real webhooks, operator UI, drift monitoring |
| Explainability | SHAP plots | Per-feature contribution in the API response, `engine` attribution, feature importance |
| Failure mode | Crashes or silent errors | Graceful degradation to defaults with explicit `source` tags, hand-weighted fallback |
| Honesty | README only | Evaluator guide, mistakes-and-learnings ledger, 24-entry bug register |
| Documentation | README only | 20+ docs, evaluator guide, business impact, mistakes log |

The complexity is **intentional depth** — every layer maps to a merchant-visible
behavior or a measured number — not accidental bloat.

## What We'd Need to Validate

Real merchant A/B test. The harness is built (`ml/ab_testing.py`, the Razorpay
webhook integration, the live-stack verification script). We need live orders
to validate the 0.50 gate on real Indian return distributions — that is the
first item on "What I'd Do Next."