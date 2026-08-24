# Graceful Failure Design

## Principle

PayShield operates on one rule: **when uncertain, be conservative and
explicit.**

In fraud and risk systems, a silent failure is worse than a loud crash. A
crash gets noticed. A silent wrong decision costs money. Every
degradation path is wired so the system falls back to a *conservative
prior*, *caps confidence*, *warns explicitly* and *leaves an audit trail*.

## Failure-Mode Matrix

| Failure | Detection | Response | Confidence | Audit |
|---------|-----------|----------|------------|-------|
| Fresh user (< 2 orders) | Feature store has no profile | Population return-rate prior (`default_new_user` provenance) | Floor (score is prior-driven) | `FRESH_USER` warning |
| Redis unavailable | `_safe_redis` degrades on every failed read | Neutral priors, no velocity/reason features (`default_redis_error`) | Floor (history unreadable) | `REDIS_UNAVAILABLE` warning |
| Thin chargeback evidence | Required-field completeness gate | `PARTIAL` rebuttal + explicit warnings | Capped at 0.70 → 0.68 | `INCOMPLETE_EVIDENCE` warning |
| GNN timeout (> 40 ms) | Timeout guard in the ensemble | L1-only fusion | Unchanged | `GNN_TIMEOUT` note |
| LLM unavailable | Health check on the investigator task | Investigation skipped; score still served | Unchanged | `LLM_SKIPPED` note |

## How Degradation Is Proven, Not Just Claimed

`python scripts/demo_graceful_failure.py` runs the three core scenarios
against the **real** `ReturnRiskScorer` (an in-memory Redis for the fresh-user
case, a `DeadRedis` that fails every read for the store-down case), and the
documented chargeback completeness gate for the evidence case. Verified
behaviour:

1. **Fresh user** → `ALLOW` / LOW tier, prior-driven score, confidence floored,
   `FRESH_USER` + provenance warnings.
2. **Redis down** → `ALLOW` / LOW tier, neutral-prior score using only
   `default_redis_error` features, velocity/reason features absent, confidence
   floored, `REDIS_UNAVAILABLE` warnings.
3. **Thin chargeback evidence** → `PARTIAL`, confidence 0.68 (cap 0.70),
   `INCOMPLETE_EVIDENCE` + capped-confidence warnings.

In all three: no crash, no overconfident rejection, an audit trail.

## Design Decision: ALLOW > BLOCK When Uncertain

The system biases toward ALLOW on fallback because:

- a false **block** costs lost revenue + CAC + churn (₹3,180 at the base
  AOV — see `docs/COST_MODEL.md`);
- a false **allow** costs return logistics (₹2,795), which is *lower* for
  most order value bands;
- MEDIUM-tier orders are flagged for merchant review before dispatch anyway;
- a blocked good customer is gone; an allowed bad return can still be chased.

## Confidence Capping

When fallback is used, confidence is never above a cap (0.70 for the
evidence path; floored by prior-dominance for the feature path). This
prevents downstream merchant systems from treating a degraded decision as
a strong signal.

## Where This Shows Up in the Live Stack

The same degradation is exercised end-to-end by `scripts/verify_live_stack.py`
(review the "weak chargeback → PARTIAL + 2 warnings" row) and by the feature
engine's `_safe_redis` guard in `return_risk/feature_engine.py`.