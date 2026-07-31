# Fraud Scoring SLO

## Service Level Objectives

| Indicator | SLO | Window | Measurement |
|-----------|-----|--------|-------------|
| Availability | 99.9% | 30 days | ratio of non-5xx / total requests |
| Latency (p99) | < 100 ms | 30 days | single-transaction scoring |
| Latency (p99) | < 500 ms | 30 days | batch-100 scoring |
| Throughput | 1000 TPS | 5 min | sustained without degradation |
| Correctness | FP rate < 5% | 7 days | at 90% recall on analyst feedback |

## Measured Baseline (2026-07-31, docker compose, 50-request run)

| Metric | Value |
|--------|-------|
| `/v1/score` p50 | 8.52 ms |
| `/v1/score` p90 | 15.02 ms |
| `/v1/score` p99 | 63.31 ms (tail = Redis feature reads + audit append; L1 rules p99 0.27 ms) |
| L2 GNN inference (CPU, per ego-graph) | p50 1.0 ms / p90 1.5 ms / p99 2.5 ms (`scripts/benchmark_gnn.py`) |
| LLM investigation (async) | ~35 s on CPU (qwen2.5:3b) — off the scoring path |
| Compliance | PCI-DSS 90/100, RBI 100/100 |

Reproduce: `python scripts/benchmark_latency.py` · `python scripts/benchmark_gnn.py`.

## SLI Queries (Prometheus)

```promql
# Availability
slo:availability:ratio_30d = (
  sum(rate(payshield_requests_total{endpoint="/v1/score",status!~"5.."}[30d]))
  / sum(rate(payshield_requests_total{endpoint="/v1/score"}[30d]))
)

# Latency p99
slo:latency:p99_30d = (
  histogram_quantile(0.99, sum(rate(payshield_request_duration_seconds_bucket{endpoint="/v1/score"}[30d])) by (le))
)

# Throughput
slo:throughput:tps_5m = sum(rate(payshield_requests_total{endpoint="/v1/score"}[5m]))

# Correctness
slo:correctness:false_positive_rate_7d = (
  sum(payshield_feedback_total{category="FALSE_POSITIVE"}[7d])
  / sum(payshield_feedback_total[7d])
)
```

## Error Budget

- 99.9% availability → 0.1% error budget = ~43 minutes downtime per month
- Budget consumed when 5xx responses exceed 0.1% of total

## Burn Rate Alerts

| Burn Rate | Budget Consumed | Response |
|-----------|----------------|----------|
| > 14.4x | 2% in 1 hour | Page on-call immediately |
| > 6x | 5% in 6 hours | Page on-call |
| > 2x | 10% in 3 days | Ticket next business day |
