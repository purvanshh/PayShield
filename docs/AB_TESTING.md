# A/B Testing — Return-Risk Weight Experiments

Champion/challenger testing for the return-risk weights, mirroring the
model-version experiments already in `ml/ab_testing.py`. Weights stay
config-driven; experiments change *which* weight set a merchant sees, not
the code.

## Lifecycle

```
POST /admin/experiments/return-risk
  {champion_weights, challenger_weights, traffic_split}
  -> experiment_id (running, 10% of merchants bucketed to challenger)

(pause)  merchant traffic flows through get_weights_for_request(merchant_id)
         - deterministic sha256 bucket per merchant (stable across runs)
         - counters incremented under ab:return_risk:{id}:traffic

POST /admin/experiments/return-risk/{id}/evaluate
  {champion: [0/1...], challenger: [0/1...]}
  -> champion_precision / challenger_precision / improvement
     significant (|delta| > 0.05) / recommendation (promote | keep)
```

Admin-gated (`model:promote` permission). The evaluation consumes observed
outcomes (pushed by the reflection task or the outcome store) — it never
fabricates them.

## Deterministic bucketing

`hash(merchant_id)` is process-random in Python; the experiment uses
`sha256(merchant_id)[0:8] % 100` so a merchant is always in the same arm
across restarts and workers. This is what makes the exposure honest: no
merchant flip-flops between treatments.

## Decisions (from the reflection loop)

- HIGH-tier precision below the 0.70 floor → recommend raising the HIGH
  gate to 0.75.
- Lost REJECTs > 30% of contests → recommend a more conservative
  completeness threshold before contesting.
- Drift in return-risk features → recommend weight retraining.

Each recommendation is produced by `agents/risk_suite_reflection.py` and
stored under `reflection:risk_suite` nightly.

## Relationship to the model A/B framework

`ABTestFramework` covers LLM/GNN model versions (challenger checkpoints).
`ReturnRiskABExperiment` covers the return-risk weight surface. Both are
admin-only, both carry `traffic_split` with an explicit promotion gate —
the scoring pipeline itself is stay-the-course unless promoted.
