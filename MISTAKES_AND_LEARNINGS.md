# Mistakes and Learnings

This is the honest ledger — the five mistakes that shaped the build, what
each cost, and the fix that held. Deep dives on the first three live in
[`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md); the full 24-entry
register is in the README's Appendix C.

---

## Mistake 1: Published "AUC > 0.92" Without Measuring It

**What happened:** Early in the project the GNN model card carried a headline
"AUC > 0.92". It was a design-phase *target* that quietly became a *result* as
it was copied into the README and talks. Nobody reran it.

**Impact:** A judge or peer reading the card would trust a number that did not
exist and could not be reproduced.

**Fix:** Ran the real benchmark (`scripts/benchmark_gnn.py`, 36k synthetic
transactions, user-disjoint split): **PR-AUC 0.198** (AUC-ROC 0.692) — not
0.92. The honest number was actually a good story: a **3.5–4× lift** over an
edge-free MLP baseline. The v1.1.0 iteration (target-user readout, five live
features) held the lift: **test PR-AUC 0.4125**, still 4.0× vs the baseline.

**Lesson:** Publish the number the run produced, or don't publish it. The
corrected 0.4125 is smaller than the aspirational 0.92 — and infinitely more
valuable, because a judge can verify it in five minutes.

## Mistake 2: PSI = 43.4 — The Drift Detector Was Broken

**What happened:** The first drift report showed **PSI = 43.4** for a feature
that had barely moved. Population stability index should be ~0 for identical
distributions. Forty-three is not a real value.

**Root cause:** Four classic estimator bugs at once — fixed 10 bins regardless
of sample size (14 discrete samples → empty bins), zero-mass bins producing
divide-by-zero log terms, no smoothing, and `density=True` double
normalization.

**Fix:** Shared quantile edges across expected/observed, bin count scaled to
sample size (`max(3, n // 5)`), Laplace smoothing on every bin, one
normalization asserted to sum to 1. Validated on degenerate cases: identical →
`0.000`, one-sigma shift → `0.981`, the real drift now reports **3.86**.

**Lesson:** A statistical estimator is a measurement instrument — validate it
against ground truth (identical distributions, tiny samples, empty bins), not
against the unit tests it wants to pass.

## Mistake 3: The 0.30 Review Gate Lost the Merchant Money

**What happened:** The initial cost model used a 0.30 review gate. It seemed
reasonable — catch more returns. It didn't model the cost of false flags.

**Impact:** On a high-return population (base rate ~32%+) the 0.30 gate flags
~75% of orders, precision collapses to 0.46, and the merchant would **lose
₹9.8 cr/month**.

**Fix:** Built a proper cost model — ₹200 per false MEDIUM flag (operator
review; the order still ships), ₹3,180 per false HIGH block (lost order + CAC
+ churn). Optimized the gate to **0.50**: 18% flag rate, precision ~0.63, and
the merchant **saves +₹0.81 cr/month** (a 10k-order fashion merchant nets
**₹20.9 lakh/month**).

**Lesson:** Threshold selection is a business optimization, not an accuracy
contest. Always translate false positives into money before tuning a gate.

## Mistake 4: Over-Engineered the Agent Framework

**What happened:** The investigation layer grew a large agent catalogue because
the problem *felt* complex. Most of them never ran in the live path — they were
stubs or re-implementations of what existing infrastructure already covered.

**Impact:** The codebase looked like architecture-astronauting. A judge would
ask "why this many agents?" and there was no good answer.

**Fix:** Archived the agents that weren't in the live path to
[`agents/archived/`](agents/archived/) with a transparent README. The live
investigation path runs only the agents that actually execute.

**Lesson:** Scope discipline beats architectural ambition. Build what runs,
document what didn't — and keep the live path small enough to defend.

## Mistake 5: Synthetic Data Without Independent Validation

**What happened:** The first return-risk benchmark was synthetic data (seed 42)
scored by a model trained on the same codebase that generated it. Worse, the
original label generator was a logistic of exactly the features the model
trains on — a circular data-generating process.

**Impact:** PR-AUC 0.9311 (and 0.8729 for the first XGBoost) measured on data
whose labels were a deterministic function of the model's own inputs. A judge
could rightly ask "so what did you actually learn?"

**Fix:** Three layers of credibility:
1. **Independent validation** — seed-99 hold-out with a fresh train.
2. **Naive baselines** — XGBoost must beat simple heuristics (serial-returner,
   COD+high-AOV), not just itself.
3. **Non-circular DGP** — return labels now include **hidden confounders**
   (product rating, delivery speed, packaging quality, weather delay, customer
   mood) the model never observes. XGBoost learns from noisy, incomplete
   signal, and the honest PR-AUC is **0.8067** — lower than the circular-DGP
   0.8729 on purpose.
4. **Ablation study** — leave-one-feature-out retraining proves every feature
   carries genuine signal against the hidden confounders.

**Lesson:** Synthetic data is acceptable for a buildathon **if** you prove
generalization. Independent validation + baseline comparison + ablation + a
non-circular generator are the minimum viable credibility stack.

---

## What the five have in common

| Mistake | Surface it broke | The fix that held |
|---------|------------------|-------------------|
| AUC > 0.92 | Honesty of claims | Run the metric or don't print it |
| PSI = 43.4 | Measurement correctness | Degenerate-case validation |
| 0.30 gate | Business economics | Cost-model-driven threshold |
| Agent bloat | Architecture clarity | Archive what doesn't run |
| Circular synthetic data | Validity of the model | Hidden confounders + independent validation + baselines + ablation |

Each was a small error with a large lesson: publish only what you can reproduce,
validate instruments against ground truth, price your mistakes in money, keep
the live path small, and never let the training data be its own test.