# Load Testing Guide — Track 2 Endpoints

## What we test

Three merchant-facing paths against the live stack, weighted like real
traffic:

| Endpoint | Workload share | Acceptance criteria (design) |
|---|---|---|
| `POST /v1/return/score` | 10/14 | p95 < 50 ms, error rate < 0.1% |
| `POST /v1/chargeback/respond` | 3/14 | p95 < 200 ms |
| `GET /v1/return/profile/{user_id}` | 1/14 | p95 < 100 ms |

## Running

```bash
# 1. stack up + demo data
make up
python scripts/seed_demo_data.py

# 2. load run (100 users is the target; start at 50, then 100)
locust -f tests/load/test_return_risk_load.py \
    --host=http://localhost:8000 \
    --users=100 --spawn-rate=10 --run-time=5m \
    --html=reports/load_test_report.html
```

Locust HTML goes to `reports/load_test_report.html`; the summary numbers
must come **from this run** — the table below is a template, not a result.

```markdown
# Load Test Report — Return-Risk + Chargeback Endpoints

**Date:** (run date)
**Environment:** Docker Compose (local), 100 concurrent users, 5 min
**Seed:** scripts/seed_demo_data.py (scenarios 1-6)

| Endpoint | RPS | p50 | p95 | p99 | Error rate |
|----------|-----|-----|-----|-----|------------|
| POST /v1/return/score | _ | _ | _ | _ | _ |
| POST /v1/chargeback/respond | _ | _ | _ | _ | _ |
| GET /v1/return/profile/{user_id} | _ | _ | _ | _ | _ |
```

## What to check while it runs

- **Redis**: `redis_feature_store_hit_rate` stays near 1.0; container CPU
  under 40%. The velocity/benford/return-risk reads are O(1) hash/zset
  reads — the hot path should not surprise. If it does, that's a finding.
- **Chargeback path**: rebuttal generation is I/O-light (audit-chain read +
  Redis) and cached after the first call (`chargeback:rebuttal:{dispute_id}`).
- **Errors**: any 5xx in Locust's failure table is a bug; 429s are the
  shared rate limiter doing its job (per-key 1000/hr default — for a 5-min
  run with 100 users use a load-test key or raise the limit via
  `RATE_LIMIT_API_KEY_PER_HOUR`).

## Expected architectural behaviour

- Return-risk scoring is read-only against Redis; the profile update is a
  background task — scoring latency should be flat under load.
- The 40 ms L2 timeout guard + L1 fallback already bound the fraud path;
  the track-2 endpoints have no such heavyweight inference at all.

## Do not

- Fabricate report numbers before the run. If the run can't happen in a
  service-less environment, say so and leave the template blank.
