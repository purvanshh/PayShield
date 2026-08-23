# Return-Risk Cost Model

Every precision/recall point in PayShield is translated into **merchant
money**. This document models the cost asymmetry of return-risk decisions
in Indian e-commerce unit economics and shows that the MEDIUM+ operating
point minimises expected merchant spend — not because it scores highest,
but because the *cost function* says so.

Interactive: `python docs/cost_model/calculator.py` (or `--scenario
electronics|grocery`, `--sensitivity`). Everything below is the exact
output of that calculator.

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

All assumptions live in [`assumptions.py`](cost_model/assumptions.py) and
per-merchant overrides in [`scenarios.json`](cost_model/scenarios.json).

## Cost of a False ALLOW (high-risk return let through)

A false allow means the order was shipped, and then it came back:

```
Direct loss = AOV + logistics + restocking + service + gateway fee
            = ₹2,500 + ₹120 + ₹80 + ₹45 + ₹50
            = ₹2,795 per missed return
```

## Cost of a False BLOCK (good customer flagged)

A false block means a good order never ships — money, gateway fee and
acquisition cost already spent, plus the expected loss of lifetime value if
the customer churns:

```
Direct   = AOV lost + gateway fee + CAC wasted
         = ₹2,500 + ₹50 + ₹180
         = ₹2,730
Indirect = churn probability × LTV
         = 0.15 × ₹3,000 = ₹450
Total    = ₹3,180 per false block
```

**The asymmetry is structural**: ₹3,180 (block) vs ₹2,795 (allow). Over
quarter-₹2.5k AOV orders the two are close, which is exactly why the
threshold is tuned for precision-leaning operation at the review tier —
every 1% of precision is ~₹27,000/month saved at 10k orders.

## PayShield Operating Points (measured)

Understanding of a tier is that the value is honest about what each gate
actually does — benchmark on a 10k-order chronological per-user hold-out.

| Tier | Threshold | Precision | Recall | Use case |
|------|-----------|-----------|--------|----------|
| HIGH | ≥ 0.70 | 1.0000 | 0.3675 | Prepaid orders: block at checkout (zero FP) |
| MEDIUM+ | ≥ 0.35 | 0.9444 | 0.9125 | COD orders: flag for review |
| LOW | < 0.35 | — | — | Normal flow |

## Scenario: Fashion Merchant, 10,000 Orders / Month

**Baseline (no scoring):**

```
1,800 returns (18% rate) × ₹2,795  = ₹50,31,000 / month
```

**With PayShield MEDIUM+ gate** (calculator output):

```
Flagged (recall)          1,642 orders
  false blocks               91 orders (5.6% of flagged, = 1 − precision)
  true catches            1,551 orders
Returns prevented         1,086 orders (70% diversion effectiveness)
Remaining returns           714 orders
False-block cost         91 × ₹3,180 = ₹2,89,380
Return cost on remaining  714 × ₹2,795 = ₹19,95,630
Total with PayShield        ₹22,85,010 / month
Net savings                 ₹27,45,990 / month   (54.6% ROI)
Annual savings              ₹3,29,51,880 (~₹3.30 Cr)
```

Per **1,000 orders**: baseline ₹5,03,100 → with PayShield ₹2,28,501 →
**net savings ₹2,74,599**.

## Scenario Sweep (calculator output, MEDIUM+ gate)

| Merchant | AOV | Return rate | False-allow/False-block | Monthly savings | Annual savings | ROI |
|----------|-----|-------------|-------------------------|-----------------|----------------|-----|
| Fashion | ₹2,500 | 18% | ₹2,795 / ₹3,180 | **₹27,45,990** | ₹3.30 Cr | 54.6% |
| Electronics | ₹8,000 | 12% | ₹8,520 / ₹9,130 | **₹56,11,550** | ₹6.73 Cr | 54.9% |
| Grocery | ₹800 | 4% | ₹961 / ₹1,036 | **₹1,94,544** | ₹23.3 L | 50.6% |

Electronics shows the leverage of high AOV: each prevented return is worth
nearly ₹8.5k, so a 12% return rate still yields ~₹56L/month. Grocery shows
the floor: at ₹800 AOV and a 4% baseline, auto-blocking makes little sense
— which is why PayShield's MEDIUM+ tier *flags for review* instead of
blocking.

## Sensitivity Analysis (AOV × return rate)

| AOV | Return rate | Monthly savings | Annual savings | ROI |
|-----|-------------|-----------------|----------------|-----|
| ₹1,500 | 12% | ₹11,53,340 | ₹1.38 Cr | 54.1% |
| ₹2,500 | 18% | ₹27,45,990 | ₹3.30 Cr | 54.6% |
| ₹4,000 | 25% | ₹59,23,930 | ₹7.11 Cr | 54.8% |

## Why MEDIUM+ Is the Optimal Point

1. **94.4% precision** → only ~1 in 18 flagged orders is a false block.
2. **91.2% recall** → ~9 of 10 genuinely high-risk users are caught.
3. **Cost symmetry**: with a false block (₹3,180) only 14% more expensive
   than a false allow (₹2,795), the MINIMISER wants high precision at the
   review tier rather than a crude block gate — catch most of the risk in
   the middle tier, and reserve the zero-false-positive HIGH gate (precision
   1.0000) for prepaid-only enforcement.

The HIGH gate is intentionally recall-light (0.3675): it exists to offer a
*provably* false-positive-free prepaid gate, not to maximise catches. The
real risk engine is the MEDIUM+ review tier.

## Usage

```bash
python docs/cost_model/calculator.py                     # fashion base case
python docs/cost_model/calculator.py --scenario grocery  # grocery merchant
python docs/cost_model/calculator.py --sensitivity       # AOV × return grid
python docs/cost_model/calculator.py --orders 10000 --operating-point HIGH
```