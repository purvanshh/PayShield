# Graceful Failure Design

## Principle

PayShield operates on one rule: **when uncertain, be conservative and
explicit.**

In risk systems, a silent failure is worse than a loud crash. A crash gets
noticed. A silent wrong decision costs money. Every degradation path is wired
so the system falls back to a *conservative prior*, *caps confidence*, *warns
explicitly* and *leaves an audit trail*.

## Failure-Mode Matrix (return-risk core)

| Failure | Detection | Response | Confidence | Audit |
|---------|-----------|----------|------------|-------|
| Fresh user (< 2 orders) | Feature store has no profile | Population return-rate prior (`default_new_user` provenance) | Floor (score is prior-driven) | `FRESH_USER` warning |
| Redis unavailable | `_safe_redis` degrades on every failed read | Neutral priors, no velocity/reason features (`default_redis_error`) | Floor (history unreadable) | `REDIS_UNAVAILABLE` warning |
| Missing merchant baseline | No merchant hash in Redis | Category lookup-table prior (`lookup_table` provenance) | Lowered | `MERCHANT_PRIOR` provenance |
| Model fails to load | `_get_xgb_model` catches load errors | Hand-weighted composite fallback (`engine: hand_weighted`) | Capped | `MODEL_FALLBACK` engine tag |

Extension failures (out-of-scope code that still exists): the chargeback
completeness gate (`PARTIAL` rebuttal, confidence cap 0.70 → 0.68,
`INCOMPLETE_EVIDENCE`) and the fraud L2 GNN timeout (L1-only fusion,
`GNN_TIMEOUT`).

## How Degradation Is Proven, Not Just Claimed

`python scripts/demo_graceful_failure.py` runs the return-risk scenarios
against the **real** `ReturnRiskScorer` — an in-memory Redis for the fresh-user
case and a `DeadRedis` that fails every read for the store-down case. Verified
behaviour:

1. **Fresh user** → LOW tier, prior-driven score, confidence floored,
   `FRESH_USER` + provenance warnings.
2. **Redis down** → LOW tier, neutral-prior score using only
   `default_redis_error` features, velocity/reason features absent, confidence
   floored, `REDIS_UNAVAILABLE` warnings.

In both: no crash, no overconfident rejection, an audit trail.

## Design Decision: Review > Block When Uncertain

The system biases toward a cheaper action on fallback because:

- a false **HIGH block** costs lost revenue + CAC + churn (₹3,180 at the base
  AOV — see `docs/COST_MODEL.md`);
- a false **MEDIUM review flag** costs ₹200 of operator time;
- MEDIUM-tier orders are flagged for merchant review before dispatch anyway;
- a blocked good customer is gone; an allowed bad return can still be chased.

## Confidence Capping

When fallback is used, confidence is never above a cap (floored by
prior-dominance for the feature path). This prevents downstream merchant
systems from treating a degraded decision as a strong signal.

## Where This Shows Up in the Live Stack

The same degradation is exercised end-to-end by the feature engine's
`_safe_redis` guard in `return_risk/feature_engine.py` and by
`scripts/verify_live_stack.py` (fresh-user and honest-customer rows).
