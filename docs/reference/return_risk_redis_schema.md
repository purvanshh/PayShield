# Return-Risk Redis Schema

**Track 02 — Phase 4.** All return-risk state lives in Redis (the existing
feature store). Keys are prefixed `return_risk:` and TTL'd (default
`feature_lookback_days: 90` → 90 days, configurable).

## 1. Hash — user profile

```
HSET return_risk:user:U001
    return_rate_30d 0.35
    return_rate_90d 0.28
    return_rate_lifetime 0.33
    total_orders 12
    total_returns 4
    avg_return_value 3200.00
    max_return_value 7000.00
    return_reason_distribution {"SIZE_ISSUE": 2, "CHANGED_MIND": 1, "DEFECTIVE": 1}
    cod_refusal_rate 0.10
    cod_refusals 1
    serial_returner_flag true
    first_return_days 9
    return_pattern_score 0.6
    last_return_ts "2026-08-15T10:00:00"
TTL 90d
```

## 2. Hash — merchant profile

```
HSET return_risk:merchant:M001
    return_rate_30d 0.28
    avg_resolution_hours 26.5
    return_fraud_rate 0.03
TTL 90d
```

## 3. Sorted set — merchant by category

```
ZADD return_risk:merchant:M001:category 0.35 fashion 0.12 electronics
TTL 90d
```

Member = category, score = return baseline. Read with `zscore` at scoring time.

## 4. Sorted set — user return velocity

```
ZADD return_risk:user:U001:returns 1723698000 "ORDER_123" 1723784400 "ORDER_124"
```

Member = order id, score = epoch ts of the return. `return_velocity_7d` =
`zcount(key, now-7d, now)`. Cleanup via `zremrangebyscore` on ingestion.

## 5. Ingestion path

`refund.created` webhook → `return_risk.ingest_refund` (not yet wired, Phase 13):
- `hincrby` totals, rewrite `return_rate_*` after each event (single-pipeline),
- `zadd` the return timestamp,
- `zremrangebyscore` old events.

## 6. Seed data

`scripts/seed_redis.py` seeds demo profiles `U001`..`U004` so the scorer
has realistic inputs on a fresh stack (see `demo-return` target later).
