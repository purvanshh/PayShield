# Synthetic Return Dataset — v1 Report

**Generated with `data.synthetic.return_generator.ReturnRiskSyntheticGenerator`
(seed 42, 20 users per archetype, 20 orders per user.)** Committed fixture:
`data/synthetic/return_dataset_v1.json` (users + merchants); the benchmark
regenerates a 100-per-archetype variant for the held-out measurements.

## Dataset composition

| Metric | Value |
|---|---|
| Users | 100 (20 per archetype) |
| Orders | 2,000 |
| Returned orders | 776 (38.8%) |
| COD share | 42.6% |
| High-risk label share (`serial_returner` or `fraud_returner`) | 40.0% |

## User archetype distribution

```
honest           20
casual_returner  20
serial_returner  20
fraud_returner   20
new_user         20
```

## Return rate by category (observed)

| Category | Observed return rate |
|---|---|
| fashion | 44.3% |
| electronics | 30.8% |
| groceries | 29.7% |
| beauty | 41.1% |
| home | 45.7% |

Categories are blended across archetypes (fraud/serial users raise the
observed rate above the pure merchant baselines in
`MERCHANT_TYPES` — expected, and the reason the scorer is evaluated on
*labels*, not on raw category rates).

## Ground-truth labels

- `high_risk=True` for users of type `serial_returner` / `fraud_returner`.
- `returned` = the simulated outcome for the order (used for secondary
  evaluation on pre-dispatch return prediction).

## Redis seeding

`python scripts/seed_return_risk_redis.py` writes `return_risk:user:*`
hashes + `:returns` zsets and `return_risk:merchant:*` hashes for the whole
fixture, so the scorer/API demo runs against real data instantly.
