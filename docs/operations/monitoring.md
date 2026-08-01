# Monitoring & Observability

## Metrics Collection

### Prometheus Metrics (hot-path instrumented)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `layer1_block_total` | Counter | `rule_class` | L1 block triggers by rule class |
| `layer2_escalation_total` | Counter | `status` | L2 outcomes by status (SUCCESS/SKIPPED_NO_GRAPH/TIMEOUT/ERROR/MODEL_UNAVAILABLE) |
| `fraud_score` | Histogram | `decision` | Final fraud score distribution by decision |
| `inference_latency_seconds` | Histogram | `source` | Per-layer latency breakdown |
| `l1_latency_seconds` | Histogram | — | L1 evaluation latency |
| `l2_latency_seconds` | Histogram | — | GNN inference latency |
| `redis_operation_total` | Counter | `operation`, `status` | Redis command success/failure counts |
| `audit_append_total` | Counter | `status` | Audit log entry append counts |

### Exposed Endpoint

```
GET /metrics
Content-Type: text/plain; version=0.0.4
```

## Alerting Rules

Defined in `prometheus/alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `HighL1BlockRate` | `layer1_block_total` > 50/min for 5 min | warning |
| `L2EscalationSpike` | `layer2_escalation_total{status=~"TIMEOUT|ERROR"}` > 10/min | critical |
| `ScoreLatencyP99High` | p99 `inference_latency_seconds` > 100 ms for 5 min | warning |
| `FraudScoreTail` | p99 `fraud_score` > 0.95 for 10 min | warning |
| `InvestigationQueueBacklog` | Celery queue depth > 100 | warning |

## Grafana Dashboards

### Available Dashboard

| Dashboard | File | Description |
|-----------|------|-------------|
| PayShield Fraud Detection | `prometheus/payshield-fraud-dashboard.json` | 4 panels: block rate (by rule class), L2 escalation spike, latency regression (p50/p90/p99), fraud-score histogram (by decision) |

### Import

```bash
# Copy to Grafana provisioning dir
cp prometheus/payshield-fraud-dashboard.json \
   grafana/provisioning/dashboards/
```

Grafana is pre-provisioned via `grafana/provisioning/` (datasource + dashboard).

## Drift Monitoring

### Feature Sampling

Every scored transaction logs per-feature values into time-scored Redis zsets:

```
drift:feat:txn_count_5m            # member "{ts}:{value}", score = timestamp
drift:feat:txn_count_1h
drift:feat:amount_total_1h
drift:feat:device_txn_count_24h
drift:feat:distinct_users_last_24h
drift:feat:distinct_merchants_1h
```

### PSI Report

Compares yesterday's distribution (T-24h..T-48h) against today's (T-24h..T) per
feature, using a robust Population Stability Index:

- **Shared quantile bin edges** on the combined distribution — no binning mismatch
- **Bin count scaled to sample size** (`max(3, n//5)`, capped at 10)
- **Laplace smoothing** — zero-mass bins cannot produce infinite/false-spike PSI

Thresholds: `< 0.1` STABLE · `0.1–0.25` MODERATE · `> 0.25` DRIFT.

```bash
# CLI (runs inside the api image; prints report + writes JSON artifact)
python scripts/run_drift_report.py

# API (same computation)
curl http://localhost:8000/admin/drift/psi -H "X-API-Key: payshield-dev-key-2026"
```

Sample output:

```
  txn_count_5m               PSI=0.0123  STABLE
  amount_total_1h            PSI=3.8608  DRIFT   <- distributions non-overlapping
  device_txn_count_24h       PSI=0.0089  STABLE
```

### Known Drift Findings (2026-07-31)

`amount_total_1h` flagged DRIFT: today's hourly aggregate (₹2.66-3.32M) vs
yesterday's baseline (₹3.99-4.99M), consistent with the seeded velocity-burst
scenario. The original PSI value (43.4) was an estimator artifact (empty bins,
no smoothing on n=14 discrete samples) — fixed in `observability/drift.py`;
corrected value 3.86, verdict unchanged. Drift reports are archived under
`observability/reports/`.

## Logging

### Log Format

```json
{
  "timestamp": "2026-07-28T12:00:00.000Z",
  "level": "INFO",
  "logger": "payshield.api",
  "request_id": "req_abc123",
  "message": "Transaction scored",
  "extra": {
    "transaction_id": "txn_001",
    "score": 0.87,
    "latency_ms": 45
  }
}
```

### Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Development only |
| INFO | Normal operations |
| WARNING | Unexpected but handled |
| ERROR | Operation failure |
| CRITICAL | System instability |

### Structured Fields

- `request_id`: Correlate requests across services
- `transaction_id`: Track specific transactions
- `latency_ms`: Performance monitoring
- `error`: Error details for debugging
- `component`: Source component

## Tracing

### Correlation IDs

Every request gets a correlation ID via `CorrelationIdMiddleware` (logged in structured JSON). No OpenTelemetry integration — deferred to future phases.

```python
# Correlation ID is automatically injected by middleware
# Logs: {"correlation_id": "c95b4e9a-...", "message": "Transaction scored"}
```
