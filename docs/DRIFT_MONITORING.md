# Drift Monitoring — Return-Risk Features

Extends the PSI drift machinery (`observability/drift.py`) to the
return-risk feature surface so a changing checkout population can't silently
degrade the scorer.

## What is tracked

`user_return_rate_30d`, `user_return_rate_90d`, `user_return_velocity_7d`,
`merchant_return_rate_30d`, `txn_amount_risk`, `user_cod_refusal_rate` —
sampled at scoring time (best-effort, hot-path safe) into
`return_risk:drift:{feature}` zsets (`{ts}:{value}` members, 30-day window).

## What the monitor does

`observability/return_risk_drift.ReturnRiskDriftMonitor.check()`:
- baseline = samples older than 24h (up to 30 days)
- current = last 24h of samples
- PSI via the shared `population_stability_index` (combined-distribution
  bin edges, Laplace smoothing, low-cardinality exact binning)
- per feature: `PSI > 0.25 → DRIFT`, `> 0.10 → WARNING`, else `STABLE`
- overall status = worst per-feature status

## Surface

```
GET /admin/drift/return-risk   (metrics:read permission)
```

```json
{
  "timestamp": "...",
  "features": {
    "user_return_rate_30d": {"psi": 0.03, "status": "STABLE", "samples": 214, "baseline_samples": 5120},
    ...
  },
  "overall_status": "STABLE"
}
```

## Feedback loop

The nightly reflection task reads `config:reflection:drift_detected` (set by
this report's consumer) and, when DRIFT, recommends a weight retraining —
the PSI + reflection pair is the whole "scorer degrades before the merchant
notices" story. Thresholds intentionally match the existing L1/L2 drift
convention so operators see one status vocabulary.

## Caveat (honest)

PSI on tiny daily windows (< ~50 samples/feature) is noisy; the monitor
reports `samples` counts alongside PSI so a low-sample WARNGING is
distinguishable from a real shift. The sampling hook records only after a
successful score response, so `samples` also tracks API traffic health.
