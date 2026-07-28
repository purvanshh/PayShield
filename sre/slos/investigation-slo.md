# Investigation SLO

## Service Level Objectives

| Indicator | SLO | Window | Measurement |
|-----------|-----|--------|-------------|
| Freshness | 60 s | 30 days | report generated within 60s of BLOCK decision |
| Availability | 99.5% | 30 days | investigation endpoint non-5xx |
| Resolution Rate | 95% | 30 days | investigations completed without manual escalation |

## SLI Queries (Prometheus)

```promql
# Freshness
slo:freshness:p60_30d = (
  histogram_quantile(0.60, sum(rate(payshield_investigation_duration_seconds_bucket[30d])) by (le))
)

# Availability
slo:investigation:availability_30d = (
  sum(rate(payshield_investigations_total{status!="error"}[30d]))
  / sum(rate(payshield_investigations_total[30d]))
)
```

## Error Budget

- 99.5% availability → 0.5% error budget = ~3.6 hours downtime per month

## Burn Rate Alerts

| Burn Rate | Budget Consumed | Response |
|-----------|----------------|----------|
| > 10x | 5% in 1 hour | Page on-call |
| > 3x | 10% in 3 days | Ticket next business day |
