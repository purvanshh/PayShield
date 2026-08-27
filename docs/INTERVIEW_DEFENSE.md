# Interview Defense — Prepared Answers

The panel asks variations of a few hard questions. These are the honest,
measured answers — every number traces to a script in this repo, and every
headline number lives in `docs/_number_manifest.json` (the single source of
truth, checked by `scripts/verify_doc_consistency.py`).

The headline framing is **Progressive Merchant Maturity**: three named scenarios
(Stage 1: Basic, Stage 2: Enriched, Stage 3: Premium). Stage 1 is the honest
floor (PR-AUC 0.8042 / ROC-AUC 0.8448, default XGBoost); Stage 3 is a premium
merchant with mature instrumentation (PR-AUC 0.9467 / ROC-AUC 0.9593). The
tuned champions reach 0.8089 / 0.8875 / 0.9483 PR-AUC.

---

## Q1: "Your PR-AUC jumped from 0.81 to 0.95. Did you just make the data easier?"

No — I created **explicit, named scenario variants**, each a different merchant
segment with a documented data-generating process. Stage 1 (PR-AUC 0.8042) is
the honest floor: 7 visible features, high hidden variance (`HIDDEN_SCALE=26`),
high label noise (0.10). Stage 3 (0.9467) is a best-case merchant with mature
instrumentation — verified product ratings and real-time delivery SLAs are
observed (9 features), hidden variance drops to `HIDDEN_SCALE=10`, label noise
to 0.05.

Both are documented, reproducible, and the **base generator was never edited**
(`git diff data/synthetic/return_risk_generator.py` is empty). The lift comes
from less unobserved variance + two more observed features + lower noise — not
from silently changing the floor. See `MISTAKES_AND_LEARNINGS.md` Mistake 7 for
why I did this instead of overwriting. One command reproduces all three:
`python scripts/run_all_scenarios.py`.

## Q2: "Why are the premium weights 10× larger than the enriched ones?"

The weights scale with **signal-to-noise**, jointly calibrated with
`HIDDEN_SCALE` and `LABEL_NOISE_STD` to hold the base rate near ~0.40 across all
stages. `HIDDEN_SCALE` drops 26→18→10 and `LABEL_NOISE` drops 0.10→0.08→0.05, so
the visible signal must be stronger in Stage 3 to keep the base rate from
drifting. If I kept the weights at Stage 2's 2.0/1.5 with `HIDDEN_SCALE=10`, the
(hidden-confounder) term would dominate and the base rate would shift — the
exact Mistake-5 trap (circular/inflated benchmark).

Crucially, the two newly-visible features are **centred** (subtract their mean
0.5) and **removed from the hidden term** once observed — so they add ranking
variance without inflating the base rate, and there's no double-counting. The
10.0/6.0 values are the single calibration knob; see the module docstring in
`data/synthetic/return_risk_generator_premium.py` for the full rationale.

## Q3: "Is 0.95 PR-AUC realistic for real data?"

Probably not for most merchants — that's exactly why it's framed as **Stage 3
(premium)**, an aspirational upper bound. Real merchants will land between
Stage 1 (0.80) and Stage 2 (0.89). The 0.95 demonstrates the model's *capacity*
when data quality is high (verified ratings, courier-API delivery tracking,
low logistics noise). The honest claim for a typical merchant is Stage 1 or
Stage 2. I deliberately did **not** lead the README with 0.95 as a single
number — the headline table shows all three stages so the floor and the ceiling
are visible together.

## Q4: "Why not use the live scorer's 0.98 PR-AUC as the headline?"

Because that's a **different task**. The `high_risk` archetype label (PR-AUC
0.9806 / ROC-AUC 0.9846 in `scripts/benchmark_return_risk.py`) combines serial-
returner + fraud archetype signals at the **user** level — it is not the
per-order `returned` label the three maturity scenarios target. Promoting it
without renaming the task would be benchmark laundering — repeating Mistake 6,
where a non-comparable 0.9311 was led alongside the defensible per-order number and
caused a ₹20.9L attribution error. The `returned` per-order label is the target in all
three maturity scenarios; the archetype benchmark stays in its own doc.

## Q5: "Your data is synthetic. Why should we trust this?"

Three reasons, each measurable:

1. **Calibrated, not fabricated.** The generator's archetypes, AOV and category
   baselines are drawn from published Indian e-commerce data (Amazon-India 2025
   category margins, ~₹74.5k AOV, ~25% COD share).
2. **Deliberately non-circular.** The return labels include **hidden confounders**
   the model never observes (packaging, weather, customer mood — and in Stage 1,
   product rating + delivery speed too) plus label noise. XGBoost learns from
   noisy, incomplete signal — exactly what real merchant data presents. The
   honest Stage-1 PR-AUC is 0.8042, *lower* than a circular DGP would produce.
3. **Triangulated with evidence.** Every feature is validated by a leave-one-
   feature-out ablation (baseline 0.8118 on the independent seed-99 hold-out),
   and the model beats two naive merchant rules on the same hold-out.

Real merchant data would change the *calibration* of the base rate and the gate,
not the architecture — which is what the "A/B test with a real merchant" next
step is built to prove.

## Q6: "Why XGBoost for 7-9 features instead of logistic regression?"

The hand-weighted composite is effectively a fixed-weight **linear** model on
the same features — it reaches PR-AUC 0.7896 on the Stage-1 hold-out. Default
XGBoost reaches 0.8042 (+0.015). That gap is the nonlinear structure the linear
model cannot express: the label depends on interactions (high recent-return-rate
× COD, high value × unknown device), and the ablation confirms it — removing
both return-rate features costs −10.5% PR-AUC even with the other five present.
Inference cost is irrelevant: 200 shallow trees, <5 ms/order on a laptop.

---

## One-line versions

- **0.81→0.95 jump?** Three named scenarios (not a silent overwrite); base
  generator untouched; reproduce with one command.
- **10× weights?** Calibrated jointly with HIDDEN_SCALE/noise to hold the ~0.40
  base rate; centred + removed from the hidden term (no double-counting).
- **0.95 realistic?** No — it's the Stage-3 ceiling; real merchants land Stage 1
  (0.80) to Stage 2 (0.89). The headline shows all three together.
- **Why not 0.98?** Different task (archetype label vs per-order `returned`);
  promoting it would repeat the Mistake-6 attribution error.
- **Synthetic?** Calibrated priors + hidden confounders + ablation + baselines;
  the lower-but-honest PR-AUC is the point.
- **Why XGBoost?** +0.015 over a linear scorer is the nonlinear signal
  (interactions); <5 ms inference.
