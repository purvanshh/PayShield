# Monitoring & Observability

## Metrics Collection

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `payshield_requests_total` | Counter | endpoint, status | Total API requests |
| `payshield_request_duration_seconds` | Histogram | endpoint | Request latency |
| `payshield_score_total` | Counter | decision | Scoring decisions |
| `payshield_model_latency` | Histogram | model_name | Per-model latency |
| `payshield_queue_depth` | Gauge | queue_name | Celery queue depth |
| `payshield_investigations_total` | Counter | status | Investigation count |
| `payshield_ensemble_confidence` | Gauge | model_name | Model confidence |
| `payshield_active_connections` | Gauge | type | WebSocket connections |
| `payshield_memory_usage_bytes` | Gauge | component | Memory consumption |
| `payshield_cpu_usage_percent` | Gauge | component | CPU utilization |

### Exposed Endpoint

```
GET /metrics
Content-Type: text/plain; version=0.0.4
```

## Alerting Rules

### Critical Alerts

```yaml
groups:
  - name: payshield-critical
    rules:
      - alert: APIHighErrorRate
        expr: rate(payshield_requests_total{status=~"5.."}[5m]) / rate(payshield_requests_total[5m]) > 0.01
        for: 2m
        labels: { severity: critical }
        annotations:
          summary: "API error rate > 1%"

      - alert: APIHighLatency
        expr: histogram_quantile(0.99, rate(payshield_request_duration_seconds_bucket[5m])) > 0.5
        for: 2m
        labels: { severity: critical }
        annotations:
          summary: "p99 latency > 500ms"

      - alert: QueueDepthCritical
        expr: payshield_queue_depth > 10000
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "Celery queue depth > 10,000"
```

### Warning Alerts

```yaml
      - alert: HighMemoryUsage
        expr: payshield_memory_usage_bytes / 1024 / 1024 / 1024 > 1.5
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "Container memory > 1.5GB"

      - alert: LowModelConfidence
        expr: payshield_ensemble_confidence < 0.6
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "Ensemble confidence below 0.6"
```

## Grafana Dashboards

### Available Dashboards

| Dashboard | Description |
|-----------|-------------|
| PayShield API | Request rate, latency, errors |
| PayShield ML | Model performance, confidence distribution |
| PayShield Queue | Celery queue depth, task processing |
| PayShield System | CPU, memory, network |
| PayShield Business | Transaction volume, approval rate |

### Import Dashboards

```bash
# API dashboard
kubectl create configmap payshield-api-dashboard --from-file=dashboards/api.json -n monitoring
```

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

### OpenTelemetry Export

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("score_transaction") as span:
    span.set_attribute("transaction_id", txn_id)
    span.set_attribute("amount", amount)
    result = ensemble.predict(features)
    span.set_attribute("score", result.score)
```

### Trace Propagation

- W3C TraceContext for distributed tracing
- Jaeger for trace visualization
- Sampling rate: 10% (100% for errors)
