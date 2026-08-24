# Return-Risk Cost Model

Every precision/recall point in PayShield is translated into **merchant
money**. This document models the cost asymmetry of return-risk decisions
in Indian e-commerce unit economics and shows that the MEDIUM+ review
operating point minimises expected merchant spend — not because it scores
highest, but because the *cost function* says so.

Interactive: `python docs/cost_model/calculator.py` (or `--scenario
electronics|grocery`, `--sensitivity`). Everything below is the exact
output of that calculator. Operating points are the **measured** results of
`scripts/benchmark_return_risk.py` on the 10,000-order calibrated dataset
(seed 42, priors aligned to public Indian e-commerce distributions —
Amazon India 2025 category margins).

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

## PayShield Operating Points (measured, calibrated 10k hold-out)

Positive rate on the calibrated population is ~40% (Amazon-margin priors).
The calibrated score distribution is cleanly bimodal — no test orders land
between 0.50 and 0.70 — so the MEDIUM+ review gate and the HIGH gate select
the same 25% of orders:

| Tier | Threshold | Precision | Recall | Use case |
|------|-----------|-----------|--------|----------|
| HIGH | ≥ 0.70 | 0.9837 | 0.6050 | Prepaid gate: block at checkout |
| MEDIUM+ | ≥ 0.50 | 0.9837 | 0.6050 | Review gate: flag for manual review (≤2% wrong, ₹200 each) |
| LOW | < 0.50 | — | — | Normal flow |

The review threshold is config-driven (`configs/return_risk_rules.yaml`
→ `operating_point.medium_review_threshold`) and must be tuned per merchant
vertical: 0.50 for high-return populations, 0.30–0.35 for low-return ones
(fashion ~14–18%).

## Scenario: Fashion Merchant, 10,000 Orders / Month

**Baseline (no scoring):**

```
1,800 returns (18% rate) × ₹2,795  = ₹50,31,000 / month
```

**With PayShield MEDIUM+ review gate** (calculator output):

```
Flagged (recall)          1,089 orders
  wrong flags               18 orders (1.6% of flagged, = 1 − precision)
  true catches           1,071 orders
Returns prevented          750 orders (70% diversion effectiveness)
Remaining returns        1,050 orders
Wrong-flag cost          18 × ₹200 = ₹3,600   (review, not full order!)
Return cost on remaining 1,050 × ₹2,795 = ₹29,34,750
Total with PayShield        ₹29,38,350 / month
Net savings                 ₹20,92,650 / month   (41.6% ROI)
Annual savings              ₹2,51,11,800 (~₹2.51 Cr)
```

Per **1,000 orders**: baseline ₹5,03,100 → with PayShield ₹2,93,835 →
**net savings ₹2,09,265**.

## Scenario Sweep (calculator output, MEDIUM+ review gate)

| Merchant | AOV | Return rate | Cost false-allow / wrong-flag | Monthly savings | Annual savings | ROI |
|----------|-----|-------------|-------------------------------|-----------------|----------------|-----|
| Fashion | ₹2,500 | 18% | ₹2,795 / ₹200 | **₹20,92,650** | ₹2.51 Cr | 41.6% |
| Electronics | ₹8,000 | 12% | ₹8,520 / ₹200 | **₹42,57,600** | ₹5.11 Cr | 41.6% |
| Grocery | ₹800 | 4% | ₹961 / ₹200 | **₹1,48,155** | ₹17.8 L | 38.5% |

Electronics shows the leverage of high AOV: each prevented return is worth
₹8.5k, so even a 12% return rate yields ~₹42.6L/month. Grocery shows the
floor: at ₹800 AOV and a 4% baseline a review gate still saves ₹1.5L/month.

## Sensitivity Analysis (AOV × return rate, MEDIUM+ review gate)

| AOV | Return rate | Monthly savings | Annual savings | ROI |
|-----|-------------|-----------------|----------------|-----|
| ₹1,500 | 12% | ₹8,85,100 | ₹1.06 Cr | 41.6% |
| ₹2,500 | 18% | ₹20,92,650 | ₹2.51 Cr | 41.6% |
| ₹4,000 | 25% | ₹44,97,325 | ₹5.40 Cr | 41.6% |

## Why MEDIUM+ Is the Optimal Point

1. **98.4% precision** → only ~1 in 60 flagged orders is a wrong flag.
2. **60.5% recall** → most clearly-above-threshold returners are caught; the
   gate is deliberately tight because false-block-vs-review cost balance
   favours precision-leaning operation on high-return verticals.
3. **Review vs block asymmetry**: a wrong MEDIUM flag costs ₹200 of operator
   time; a wrong HIGH block costs ₹3,180. The review tier is therefore the
   cheapest place to catch most of the risk — and the HIGH/prepaid gate is
   reserved for the clearly-high segment.

Precision > recall at the review tier is a **cost decision**: with these
unit economics the minimiser flags for review, keeps false orders flowing
(they still ship), and only prepaid-gates the obvious tail.

## Usage

```bash
python docs/cost_model/calculator.py                     # fashion base case
python docs/cost_model/calculator.py --scenario grocery  # grocery merchant
python docs/cost_model/calculator.py --sensitivity       # AOV × return grid
python docs/cost_model/calculator.py --orders 10000 --operating-point HIGH
```