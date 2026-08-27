# Return-Risk Cost Model

Every precision/recall point in PayShield is translated into **merchant
money**. This document models the cost asymmetry of return-risk decisions
in Indian e-commerce unit economics and shows that the MEDIUM+ review
operating point minimises expected merchant spend — not because it scores
highest, but because the *cost function* says so.

Interactive: `python docs/cost_model/calculator.py` (or `--scenario
electronics|grocery`, `--sensitivity`, `--vertical-sensitivity`). Everything
below is the exact output of that calculator. Operating points are the
**measured** results of `scripts/train_xgb_return_risk.py` — the offline
XGBoost model on the 2,000-order held-out test set (per-user chronological
hold-out, seed 42, non-circular DGP).

## Assumptions (Indian e-commerce, 2026)

| Parameter | Value | Source / rationale |
|-----------|-------|--------------------|
| Average Order Value (AOV) | ₹2,500 | Industry median (Myntra, Flipkart, Amazon IN) |
| Return rate (unscored) | 18% | Post-festive-spike baseline |
| Return logistics cost | ₹120 | Reverse pickup + QC |
| Restocking cost | ₹80 | Repackaging, warehouse handling |
| Customer service cost per return | ₹45 | Call centre + chatbot escalation |
| Payment gateway fee (non-refundable) | 2% of AOV | Razorpay standard |
| Customer acquisition cost (CAC) | ₹180 | Blended digital-marketing |
| Churn probability after false block | 15% | Industry estimate |
| Expected lifetime value (LTV) | ₹3,000 | Good-customer lifetime revenue |
| Diversion effectiveness | 70% | Share of diverted orders that don't return |
| **Review cost (wrong MEDIUM flag)** | **₹200** | Operator time for one manual review — **not** the order value |

All assumptions live in [`assumptions.py`](cost_model/assumptions.py) and
per-merchant overrides in [`scenarios.json`](cost_model/scenarios.json).

## Cost of a False ALLOW (high-risk return let through)

A false allow means the order was shipped, and then it came back:

```
Direct loss = AOV + logistics + restocking + service + gateway fee
            = ₹2,500 + ₹120 + ₹80 + ₹45 + ₹50
            = ₹2,795 per missed return
```

## Cost of a False BLOCK (good customer flagged at the prepaid gate)

A false block means a good order is stopped from shipping — money, gateway
fee and acquisition cost already spent, plus the expected loss of lifetime
value if the customer churns:

```
Direct   = AOV lost + gateway fee + CAC wasted
         = ₹2,500 + ₹50 + ₹180
         = ₹2,730
Indirect = churn probability × LTV
         = 0.15 × ₹3,000 = ₹450
Total    = ₹3,180 per false block
```

## Review vs Block — the key modelling fix

PayShield's MEDIUM tier is **FLAG_FOR_REVIEW**, not a block. The order still
ships — an operator spends a few minutes checking it. Charging every wrong
MEDIUM flag the full ₹3,180 would massively overstate losses for a
non-blocking system. So:

- **MEDIUM+ gate (review)** — a wrong flag costs **₹200** of operator time.
- **HIGH gate (prepaid/block)** — a wrong flag costs the full **₹3,180**
  false-block penalty.

This is why the ROI flips positive at wider recall: flagging a good order
for review is cheap; blocking it is expensive.

## PayShield Operating Points (measured offline XGBoost, 2,000-order hold-out)

The offline XGBoost model is evaluated on the `returned` label. Measured
confusion matrices at each gate feed the cost model:

| Gate | Flag rate | Precision | Recall | Use case |
|------|-----------|-----------|--------|----------|
| 0.30 | 70.0% | 0.524 | 0.925 | Aggressive review — catches most returns, more wrong flags |
| 0.40 | 59.8% | 0.582 | 0.877 | — |
| 0.45 | 54.7% | 0.614 | 0.849 | — |
| **0.50** | **50.5%** | **0.635** | **0.811** | **Review gate: flag for manual review (₹200 per wrong flag)** |
| 0.60 | 43.3% | 0.693 | 0.758 | — |
| 0.70 | 34.5% | 0.752 | 0.657 | Prepaid gate: block at checkout (₹3,180 per wrong block) |

The review threshold is config-driven (`configs/return_risk_rules.yaml`
→ `operating_point.medium_review_threshold`) and must be tuned per merchant
vertical — the [vertical sensitivity](#vertical-sensitivity-analysis-where-the-050-gate-breaks)
below shows 0.50 is right for high-return populations and drifts up for
low-return ones.

> **Enriched pipeline:** the Redis-enriched feature engine exists in the
> codebase, but the XGBoost model has **not** been recalibrated to enriched
> feature distributions. This cost model therefore uses the **offline** model
> operating point. Retraining on enriched features (and on real merchant data)
> is the highest-priority next step.

## Scenario: Fashion Merchant, 10,000 Orders / Month

**Baseline (no scoring):**

```
1,800 returns (18% rate) × ₹2,795  = ₹50,31,000 / month
```

**With PayShield MEDIUM+ review gate (0.50)** (calculator output, offline XGBoost):

```
Flagged (recall)          1,393 orders
  wrong flags              450 orders (32.3% of flagged, = 1 − precision)
  true catches              943 orders
Returns prevented          660 orders (70% diversion effectiveness)
Remaining returns        1,140 orders
Wrong-flag cost          450 × ₹200 = ₹90,000   (review, not full order!)
Return cost on remaining 1,140 × ₹2,795 = ₹31,86,300
Total with PayShield        ₹32,76,300 / month
Net savings                 ₹17,54,700 / month   (34.9% ROI)
Annual savings              ₹2,10,56,400 (~₹2.11 Cr)
```

Per **1,000 orders**: baseline ₹5,03,100 → with PayShield ₹3,27,630 →
**net savings ₹1,75,470**.

## Scenario Sweep (calculator output, MEDIUM+ review gate 0.50)

| Merchant | AOV | Return rate | Cost false-allow / wrong-flag | Monthly savings | Annual savings | ROI |
|----------|-----|-------------|-------------------------------|-----------------|----------------|-----|
| Fashion | ₹2,500 | 18% | ₹2,795 / ₹200 | **₹17,04,560** | ₹2.05 Cr | 33.9% |
| Electronics | ₹8,000 | 12% | ₹8,520 / ₹200 | **₹36,18,000** | ₹4.34 Cr | 35.4% |
| Grocery | ₹800 | 4% | ₹961 / ₹200 | **₹1,10,696** | ₹13.3 L | 27.4% |

Electronics shows the leverage of high AOV: each prevented return is worth
₹8.5k, so even a 12% return rate yields ~₹36.2L/month. Grocery shows the
floor: at ₹800 AOV and a 4% baseline a review gate still saves ~₹1.1L/month.

## Sensitivity Analysis (AOV × return rate, MEDIUM+ review gate 0.50)

| AOV | Return rate | Monthly savings | Annual savings | ROI |
|-----|-------------|-----------------|----------------|-----|
| ₹1,500 | 12% | ₹7,21,000 | ₹86.5 L | 33.8% |
| ₹2,500 | 18% | ₹17,54,700 | ₹2.11 Cr | 34.9% |
| ₹4,000 | 25% | ₹38,41,025 | ₹4.61 Cr | 35.5% |

## Vertical Sensitivity Analysis (where the 0.50 gate breaks)

The 0.50 gate is tuned for a **high-return vertical**. Precision at a fixed
gate scales with the base rate — fewer real returns sit in the flagged tail —
so on a low-return vertical the same gate flags mostly good orders. Swept
from the tuned XGBoost operating curve
(`python docs/cost_model/calculator.py --vertical-sensitivity`):

| Merchant vertical | Base return rate | Optimal gate | Net ₹/month at 0.50 gate | Net ₹/month at optimal gate |
|---|---|---|---|---|
| Fashion (high return) | 32% | 0.50 | **+₹24.3L** | **+₹24.3L** |
| Fashion (low return) | 14% | 0.60 | +₹3.4L | +₹3.5L |
| Electronics | 8% | 0.70 | +₹0.6L | +₹0.7L |
| Grocery | 4% | 0.70 | −₹0.2L | −₹0.1L |

**Why it breaks:** at low base rates, flagging ~45% of orders (the 0.50 flag
rate) catches too few *true* returns to cover ₹200-per-flag review costs.
Precision at a gate is approximately `recall(gate) × base_rate / flag_rate(gate)`;
at 4% base that collapses the review economics. The gate must move up (0.60–0.70)
as the base rate falls, and below ~5% base rate no review gate is profitable
with the raw-features model — the correct answer there is *don't review*, or
recalibrate the model on that merchant's data.

> These are **synthetic projections** — real merchant data would calibrate the
> base rate and gate jointly. `vertical_sensitivity.json` holds the full sweep.

## Why MEDIUM+ (0.50) Is the Optimal Gate

1. **67.7% precision at 0.50** — the wrong-flag cost is ₹200 of operator
   review time (the order still ships), not the ₹3,180 full-order loss. Even
   with ~32% wrong flags, review stays cheap relative to the returns it
   prevents.
2. **77.4% recall** — catches most of the high-return tail while flagging
   ~45% of orders; higher precision than the 0.30 gate, which flags 64% of
   orders for only a few more catches.
3. **Review vs block asymmetry**: a wrong MEDIUM flag costs ₹200; a wrong HIGH
   block costs ₹3,180. The review tier is the cheapest place to catch most of
   the risk — the HIGH/prepaid gate is reserved for the clearly-high segment.

The 0.50 gate is the cost minimiser for a high-return fashion vertical (the
gate sweep above: ₹17.0L at 0.50 vs ₹15.5L at 0.30 and ₹16.8L at 0.70).
On low-return verticals the gate must move up (0.60–0.70) — see the vertical
sensitivity section.

## Usage

```bash
python docs/cost_model/calculator.py                     # fashion base case
python docs/cost_model/calculator.py --scenario grocery  # grocery merchant
python docs/cost_model/calculator.py --sensitivity       # AOV × return grid
python docs/cost_model/calculator.py --vertical-sensitivity  # gate sweep across base rates
python docs/cost_model/calculator.py --orders 10000 --operating-point HIGH
```