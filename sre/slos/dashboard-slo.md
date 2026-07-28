# Dashboard SLO

## Service Level Objectives

| Indicator | SLO | Window | Measurement |
|-----------|-----|--------|-------------|
| Availability | 99.5% | 30 days | dashboard API non-5xx |
| Latency (p95) | < 2 s | 30 days | page load time |
| Data Freshness | < 30 s | 30 days | data lag behind API |

## SLI Queries (Prometheus)

```promql
# Availability
slo:dashboard:availability_30d = (
  sum(rate(payshield_dashboard_requests_total{status!~"5.."}[30d]))
  / sum(rate(payshield_dashboard_requests_total[30d]))
)

# Latency
slo:dashboard:latency_p95_30d = (
  histogram_quantile(0.95, sum(rate(payshield_dashboard_duration_seconds_bucket[30d])) by (le))
)
```

## Error Budget

- 99.5% availability → 0.5% error budget = ~3.6 hours downtime per month
