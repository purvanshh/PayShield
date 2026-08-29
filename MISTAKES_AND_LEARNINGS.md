# Mistakes and Learnings

This is the honest ledger — the six mistakes that shaped the build, what
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

**Fix:** Ran the real GNN benchmark (36k synthetic transactions, user-disjoint
split): **PR-AUC 0.198** (AUC-ROC 0.692) — not 0.92. The honest number was
actually a good story: a **3.5–4× lift** over an edge-free MLP baseline. The
v1.1.0 iteration (target-user readout, five live features) held the lift:
**test PR-AUC 0.4125**, still 4.0× vs the baseline.

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

## Mistake 3: The 0.30 Review Gate Was Chosen by Accuracy Intuition, Not Cost

**What happened:** The initial review gate (0.30) was picked to "catch more
returns." It didn't model the cost of false flags, and on a high-return
population the reconstructed-data runs showed a 0.30 gate can flag ~75% of
orders with collapsed precision — losing money.

**Impact:** On the reconstructed Amazon 2025 population a 0.30 gate would have
cost the merchant ₹9.8 cr/month (75% flag rate, precision ~0.46).

**Fix:** Built a proper cost model — ₹200 per false MEDIUM flag (operator
review; the order still ships), ₹3,180 per false HIGH block (lost order + CAC
+ churn). The measured offline-model sweep shows **0.50 is optimal for
high-return verticals** (₹17.5L at 0.50 vs ₹16.3L at 0.30), and the gate is
config-driven per vertical.

**Lesson:** Threshold selection is a business optimization, not an accuracy
contest. Always translate false positives into money before tuning a gate.

## Mistake 4: Over-Engineered the Agent Framework

**What happened:** The investigation layer grew a large agent catalogue because
the problem *felt* complex. Most of them never ran in the live path — they were
stubs or re-implementations of what existing infrastructure already covered.

**Impact:** The codebase looked like architecture-astronauting. A judge would
ask "why this many agents?" and there was no good answer.

**Fix:** Archived the agents that weren't in the live path and, in the final
scope pass, removed the agent framework entirely — the return-risk scorer runs
the features → rules → XGBoost path directly, with no orchestration layer.

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

## Mistake 6: The 0.9311 / ₹20.9L Attribution Error

**What happened:** The README led with two PR-AUC numbers — 0.8067 (offline
XGBoost) and 0.9311 (Redis-enriched). These were **not comparable**: different
labels (`returned` vs. `high_risk` archetype), different engines (XGBoost vs.
hand-weighted), different data generators. The ₹20.9L cost model was tied to
the 0.9311 operating point, not the evaluated model.

**Why it matters:** In a track about honest metrics, leading with a
non-comparable "better" number signals either incompetence or dishonesty.
Neither is acceptable.

**The fix:** Removed 0.9311 from all headline surfaces. The single defensible
number is offline XGBoost **0.8067** → **₹17.5L** at the 0.50 gate (P 0.677,
R 0.774, measured confusion matrix). The enriched feature pipeline is
documented as future work (the XGBoost model has not been recalibrated to its
distributions), and the generator-design limitation is documented in
`docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`. Added this entry.

**Lesson:** When you have two numbers that measure different things, pick the
one you can defend and explain why the other exists but isn't comparable.
Don't let the higher number lead.

---

## Mistake 7: [Prevented] Silent DGP overwrite for higher metrics

**What we considered:** To get PR-AUC above 0.90 on the `returned` label,
changing `HIDDEN_SCALE` and `LABEL_NOISE_STD` in the base generator
(`data/synthetic/return_risk_generator.py`) and retraining, without documenting
the change as a different scenario.

**Why it's wrong:** It repeats Mistake 5 (the circular DGP that gave a fake
0.9311) and Mistake 6 (the benchmark mismatch that caused the ₹20.9L attribution
error). An evaluator comparing the new 0.94 to the old 0.8067 could not tell
whether the improvement came from better modeling or from easier data — the
single most damaging ambiguity in a metrics-honesty track.

**What we did instead:** Created explicit named scenario variants —
`return_risk_generator_enriched.py` (Stage 2) and
`return_risk_generator_premium.py` (Stage 3) — each with documented DGP
parameters (visible-feature set, `HIDDEN_SCALE`, `LABEL_NOISE_STD`, seed). Each
scenario is a *different merchant segment*, not a replacement: Stage 2 exposes
`product_rating` and `delivery_speed_days` (a real segment — marketplaces record
ratings and delivery SLAs) and lowers the hidden variance; Stage 3 represents a
premium merchant with mature instrumentation. The base generator is **untouched**
— Stage 1's floor stays auditable (PR-AUC 0.7991 default / 0.8089 tuned). ROC-AUC
is measured (`roc_auc_score`), never hardcoded, fixing Mistake 1. The whole
comparison reproduces with one command: `python scripts/run_all_scenarios.py`.

**Lesson:** When you need a higher number to make a point about data maturity,
make the *scenario* the unit of comparison — documented, named, reproducible —
never a silent edit to the generator that produced the floor.

---

## What the seven have in common

| Mistake | Surface it broke | The fix that held |
|---------|------------------|-------------------|
| AUC > 0.92 | Honesty of claims | Run the metric or don't print it |
| PSI = 43.4 | Measurement correctness | Degenerate-case validation |
| 0.30 gate | Business economics | Cost-model-driven threshold |
| Agent bloat | Architecture clarity | Archive what doesn't run |
| Circular synthetic data | Validity of the model | Hidden confounders + independent validation + baselines + ablation |
| 0.9311 attribution | Comparability of metrics | Pick the defensible number; document the rest |
| Silent DGP overwrite (prevented) | Scenario honesty | Named, documented maturity scenarios; base generator untouched |

Each was a small error with a large lesson: publish only what you can reproduce,
validate instruments against ground truth, price your mistakes in money, keep
the live path small, and never let the training data be its own test.