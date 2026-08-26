# Interview Defense — Prepared Answers

Four questions are near-certain in the panel. These are the honest, measured
answers — every number traces to a script in this repo.

---

## Q1: "Why XGBoost for 7 features instead of logistic regression?"

The hand-weighted composite is effectively a fixed-weight **linear** model on
the same seven features — it reaches PR-AUC 0.7896 on the hold-out. Tuned
XGBoost reaches **0.8067** (+0.017). That gap is the nonlinear structure the
linear model structurally cannot express: the label depends on interactions
(e.g. high recent-return-rate × COD, high value × unknown device), and the
ablation confirms it — removing both return-rate features costs −10.5% PR-AUC
even with the other five present.

So the honest framing is: the linear baseline was already near-optimal on the
linear part of the signal, and XGBoost's edge is the residual nonlinearity. A
logistic regression would land where the hand-weighted scorer does (≈0.79),
not where XGBoost does (0.807). Inference cost is irrelevant here — the tuned
model is 200 shallow trees, well under 5 ms per order on a laptop, so there is
no complexity tax for the capacity gain. We keep the linear scorer anyway, as
the transparent fallback when the model file is absent.

## Q2: "You spent 5 days and built Redis, Postgres, Neo4j, React, Kubernetes. Did you over-engineer?"

The **evaluated return-risk surface is small and hermetic**. The model path
runs with zero services: `scripts/train_xgb_return_risk.py`,
`scripts/ablation_study.py`, `scripts/tune_xgb.py` and
`docs/cost_model/calculator.py` all run standalone on a laptop. The seven
feature inputs are plain numbers; the scorer (`return_risk/`) is a few hundred
lines of Python.

The infrastructure exists for the things the brief actually asks about: the
**enriched feature pipeline** (Redis holds the user/merchant history the live
scorer runs on — though the XGBoost model has not yet been recalibrated to it,
which is the honest next step), and the **platform extensions** (fraud/
chargeback on the same audit chain), which are explicitly demoted to future
work in the README. Everything else — Postgres, Neo4j, Ollama, the Celery
workers, the React dashboard and the k8s manifests — was **removed in a
deliberate scope cut**: the repo went from ~40 top-level directories to ~19
and from 579 tests to 455, all still green. If I had 24 hours, I'd keep Redis
and the return-risk evidence scripts exactly as they are and spend any saved
time on the vertical-sensitivity analysis now in `docs/COST_MODEL.md`.

## Q3: "Your data is synthetic. Why should we trust this?"

Three reasons, each measurable:

1. **Calibrated, not fabricated.** The generator's archetypes, AOV and
   category baselines are drawn from published Indian e-commerce data
   (Amazon-India 2025 category margins, ~₹74.5k AOV, ~25% COD share) — see the
   generator docstring.
2. **Deliberately non-circular.** The return labels include **hidden
   confounders** the model never observes (product rating, delivery speed,
   packaging, weather delay, customer mood) plus label noise. XGBoost learns
   from noisy, incomplete signal — which is exactly the situation real merchant
   data presents. The honest PR-AUC is **0.8067**, *lower* than a circular
   DGP would produce, and we say so in the README.
3. **Triangulated with evidence.** Every feature is validated by a
   leave-one-feature-out ablation, and the model beats two naive merchant rules
   on the same hold-out. The enriched feature pipeline exists but is honestly
   scoped as future work — the model has not been recalibrated to it.

Real merchant data would change the *calibration* of the base rate and the
gate — it would not invalidate the architecture. That is precisely what the
"A/B test with a real merchant" next step is built to prove.

## Q4: "Your README used to claim 0.9311. What happened?"

> We found that 0.9311 was the hand-weighted scorer on the `high_risk`
> archetype label — different target, different engine, different generator
> than the evaluated XGBoost model. It wasn't a comparable "better" number; it
> was a different metric. We removed it and now lead with the single defensible
> number: **0.8067 on the `returned` label**, which ties to **₹17.5L** in the
> cost model. The enriched pipeline is real code, but recalibrating XGBoost to
> it — and ideally to real merchant data — is the next step, not a headline.

---

## One-line versions

- **Why XGBoost?** The +0.017 over a linear scorer is the nonlinear signal
  (interactions); it costs <5 ms at inference.
- **Over-engineered?** The evaluated model runs hermetically with zero
  services; the infrastructure is the enriched pipeline and the extensions.
- **Synthetic data?** Calibrated priors + hidden confounders + ablation +
  baselines; the lower-but-honest PR-AUC is the point.
- **What happened to 0.9311?** It was a different metric (archetype label,
  hand-weighted); we removed it and lead with the defensible 0.8067.