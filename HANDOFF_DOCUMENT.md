# PayShield v1.0.0 Handoff Document

## Project Summary

PayShield is a real-time UPI fraud detection system with three-layer scoring:
L1 statistical filter (sub-millisecond, 12 configurable rules), L2 graph neural
network (conditional fusion, 40 ms timeout guard, five status codes), and L3
async LLM investigation (Celery + Ollama qwen2.5:3b). Delivered over 10
implementation phases. 392 tests at 74% coverage.

## System Capabilities

| Capability | Details |
|------------|---------|
| Transaction Scoring | Real-time (p50 8.5 ms, p99 63.3 ms), batch (up to 100), idempotent replay |
| L2 GNN | Conditional fusion for returning users (≥ 2 graph nodes); 40 ms timeout; SKIPPED_NO_GRAPH for fresh users; L1 fallback on TIMEOUT/ERROR |
| L3 Investigation | Async Celery + Ollama (qwen2.5:3b), ~35 s, JSON reports with quality scores |
| Agent System | 14 agents (12 concrete + router + state), 27 tests covering all message types |
| Auth | API Key (SHA-256 hashed) + JWT (HS256) + TOTP MFA (RFC 6238, pure stdlib) |
| Rate Limiting | Per-API-key 1000/hr + per-user limit via Redis incr+TTL; 429 with Retry-After |
| Audit | Hash-chained, tamper-evident JSONL + async queue (<1ms hot-path append) |
| Observability | Prometheus metrics (hot-path counters/histograms), Grafana (4 panels), PSI drift |
| Compliance | PCI-DSS 90/100, RBI 100/100, EU AI Act 100/100 (13 controls) |
| Dashboard | Vite+React skeleton (Dashboard, Investigation, Login) |

## Architecture Decision Records

### ADR-001: Three-Layer Scoring over Monolithic Model
- **Decision**: L1 statistical rules → L2 conditional GNN → L3 async LLM
- **Rationale**: L1 handles obvious patterns in < 1 ms; L2 catches relational anomalies (mule rings); L3 provides explainability. Conditional fusion prevents fresh-user false positives.
- **Trade-off**: L2 doesn't run on every transaction (~40% coverage)

### ADR-002: Celery + Redis over Kafka
- **Decision**: Celery + Redis for async investigation processing
- **Rationale**: Investigation volume is low (only BLOCK/REVIEW triggers); Celery is simpler to operate
- **Trade-off**: No replay capability out of box; not suitable for high-throughput streaming

### ADR-003: FastAPI over Django
- **Decision**: FastAPI for API layer
- **Rationale**: Native async support, Pydantic validation, auto-generated OpenAPI docs
- **Trade-off**: Fewer built-in features (admin panel, ORM admin)

### ADR-004: PostgreSQL + Redis over single database
- **Decision**: PostgreSQL (transactional) + Redis (feature store, cache, broker)
- **Rationale**: Redis provides sub-ms feature reads for L1 velocity/geo/Benford rules; PostgreSQL ensures ACID for audit metadata
- **Trade-off**: Two data stores to operate and back up

### ADR-005: Conditional GNN Fusion over Always-On GNN
- **Decision**: `_run_l2_inference` with 5 status codes (SUCCESS / SKIPPED_NO_GRAPH / TIMEOUT / MODEL_UNAVAILABLE / ERROR); L1 fallback on any non-SUCCESS status
- **Rationale**: Fresh users with empty ego-graphs would get random noise from the GNN. 40 ms timeout prevents blocking the hot path on slow inference. Availability over perfection.
- **Trade-off**: ~60% of transactions skip L2; collaborative fraud patterns on new users are caught by L1 velocity rules

## Handoff Checklist

### For Operations Team

- [ ] Docker Compose stack: `docker compose -f docker/docker-compose.yml up`
- [ ] Kubernetes manifests: `k8s/base/` (16 manifests, overlays minimal)
- [ ] Redis LRU config: `maxmemory-policy allkeys-lru` (checked at startup via `ensure_memory_policy`)
- [ ] Prometheus scraping: `GET /metrics` on port 8000
- [ ] Grafana: import `prometheus/payshield-fraud-dashboard.json`
- [ ] Alert rules: `prometheus/alerts.yml` (block rate, escalation spike, latency, queue backlog)
- [ ] Environment variables: copy `.env.example` → `.env` (all vars documented)
- [ ] Ollama: `ollama pull qwen2.5:3b` for LLM investigations

### For Development Team

- [ ] Python 3.11+: `pip install -r requirements.txt`
- [ ] Test venv: `.venv-test/bin/python -m pytest tests/ -q` (392 tests)
- [ ] Coverage gates: TOTAL ≥ 70%, score.py ≥ 80%, ensemble.py ≥ 80%, graph_feature_engine.py ≥ 80%
- [ ] Model card: `python scripts/generate_model_card.py` (auto-generated from benchmark JSON)
- [ ] Fairness audit: `python models/fairness_audit.py`
- [ ] EU AI Act check: `python -c "from compliance.eu_ai_act import EUAiActComplianceChecker; print(EUAiActComplianceChecker().run().score)"`

### For On-Call Engineers

- [ ] Incident runbooks: `sre/runbooks/`
- [ ] PSI drift check: `GET /admin/drift/psi` (daily)
- [ ] L2 status distribution: Prometheus `layer2_escalation_total` by status
- [ ] Audit chain verification: `store/audit_log.py:verify_chain()`

## Known Limitations

| Limitation | Status |
|------------|--------|
| GNN conditional fusion only (not every live decision — ~40% coverage) | Architectural choice — fresh users produce empty ego-graphs |
| Auto-model promotion requires manual approval | Manual `POST /admin/models/promote` step |
| Dashboard UI is minimal | 3-page Vite+React skeleton with inline styles |
| K8s overlays not customized for staging/prod | 16 base manifests exist; overlay env-specific config needed |
| Agents tested in isolation (27 tests) — no live orchestration | 14 agents exist; full swarm consensus is deferred |
| GNN trained on synthetic data (30k transactions) | Real UPI data has different seasonality |
| P2P edges defined in schema but not created from live transactions | Defined; population deferred |
| No distributed tracing (OpenTelemetry) | Logs with correlation IDs available; not wired to Jaeger/Sentry |

## Configuration Reference

### Core Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET` | HS256 signing key | `payshield-jwt-secret-dev-2026` |
| `JWT_REFRESH_DAYS` | Refresh token sliding window | `7` |
| `PAYSHIELD_DEV_API_KEY` | Dev API key | `payshield-dev-key-2026` |
| `FRONTEND_URL` | CORS allowed origin | `http://localhost:3000` |
| `RATE_LIMIT_API_KEY_PER_HOUR` | Per-key rate limit | `1000` |
| `RATE_LIMIT_USER_PER_HOUR` | Per-user rate limit | `1000` |
| `REDIS_HOST` / `REDIS_PORT` | Redis connection | `localhost:6379` |
| `ENCRYPTION_KEY` | AES-256 key for data at rest | (required) |
| `ENFORCE_RBAC` | Enable RBAC | `true` |
| `DATA_REGION` | Data residency region | `IN` |
| `ENABLE_LLM_INVESTIGATOR` | L3 async investigations | `true` |

### Operational Runbooks

- **Disaster Recovery**: `dr/DR_RUNBOOK.md`
- **Deployment**: `docs/operations/deployment.md`
- **Troubleshooting**: `docs/operations/troubleshooting.md`
- **Monitoring**: `docs/operations/monitoring.md`
- **Interview prep**: `STUDY_GUIDE.md`
- **Audit status**: `AUDIT_REPORT_v2.md`
