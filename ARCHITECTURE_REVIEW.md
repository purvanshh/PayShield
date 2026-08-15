# PayShield Architecture Review — v2 (Post-Phase-10)

## Executive Summary

PayShield is a real-time UPI fraud detection system with three-layer scoring:
L1 statistical filter (sub-millisecond rule evaluation), L2 graph neural network
(conditional fusion with 40 ms timeout guard), and L3 async LLM investigation
(Celery + Ollama qwen2.5:3b). Delivered over 10 implementation phases.

**Measured latency:** p50 8.5 ms, p90 15.0 ms, p99 63.3 ms for `/v1/score`.

## Architecture (C4 Model)

### Context
```
[UPI Transaction] → [PayShield API] → [L1 Rules / L2 GNN / L3 LLM] → [Decision]
```

### Containers
- **FastAPI** — REST + WebSocket API gateway (port 8000)
- **Celery** — Async task queue for LLM investigations (Redis broker)
- **PostgreSQL** — Transactional data + audit metadata (SQLAlchemy + asyncpg)
- **Redis** — Feature store (velocity/geo/Benford), Celery broker, rate limiter, investigation cache
- **Ollama** — Local LLM inference (qwen2.5:3b, CPU, ~35 s per investigation)
- **React Dashboard** — Vite+React skeleton (3 pages: Dashboard, Investigation, Login)

### Components
- 3-layer scoring: L1 statistical filter (12 configurable rules) → L2 GNN (conditional fusion) → Ensemble (weighted + isotonic calibration)
- L3 async LLM investigator (structured JSON prompts, tolerant parser)
- 14-agent framework (12 concrete agents + router + state, tested in isolation)
- Prometheus metrics + Grafana dashboard (4 panels)
- 392 tests at 74% coverage (gates: score 91%, ensemble 90%, graph 99%)

## Technology Stack

| Layer | Choice | Justification |
|-------|--------|--------------|
| API | FastAPI | Async, Pydantic validation, auto-docs |
| ML | PyTorch Geometric | HeteroConv + SAGEConv for heterogeneous graph fraud detection |
| Feature store | Redis | Sub-ms reads for velocity/geo features |
| Queue | Celery + Redis | Simple ops, sufficient for async investigations |
| DB | PostgreSQL 16 | ACID, JSON, mature ecosystem |
| Cache | Redis 7 | Multi-purpose (broker, cache, feature store, rate limiter) |
| LLM | Ollama (qwen2.5:3b) | Local inference, no API dependency |
| Auth | JWT (HS256) + API Key + TOTP MFA | Refresh rotation, per-key/per-user rate limits |

## Performance Baseline (measured, 2026-08-01)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| p50 latency (`/v1/score`) | 8.5 ms | < 50 ms | PASS |
| p90 latency | 15.0 ms | < 100 ms | PASS |
| p99 latency | 63.3 ms | < 200 ms | PASS |
| L1 rule evaluation (p99) | 0.27 ms | < 1 ms | PASS |
| GNN inference (CPU, per ego-graph, v1.1.0) | p99 0.70 ms | < 5 ms | PASS |
| PR-AUC (lead metric) | 0.4125 (4.0× baseline) | > 2× prevalence | PASS |
| AUC-ROC | 0.7668 | > 0.65 | PASS |
| Test coverage | 74% | > 70% | PASS |
| Tests | 392 passed | > 300 | PASS |

## Security Posture

- **Authentication**: JWT (HS256) with 7-day sliding refresh rotation + API Key (SHA-256 hashed) + TOTP MFA (RFC 6238, SHA-1, 30s step, pure stdlib)
- **Rate Limiting**: Per-API-key 1000 req/hr + per-user limits via Redis incr+TTL; 429 with Retry-After header; IP-based sliding window (200 req/min) as coarse guard
- **Authorization**: RBAC on all admin endpoints (`require_permission`), roles: system/admin/analyst
- **CORS**: Env-driven `FRONTEND_URL` (no wildcard), security headers middleware (CSP, HSTS)
- **Encryption**: AES-256 at rest via `ENCRYPTION_KEY`, TLS in transit
- **Audit**: Hash-chained, tamper-evident JSONL log with PII masking; async queue-backed (`<1ms` append)
- **Compliance**: PCI-DSS 90/100, RBI 100/100, EU AI Act 100/100 (13 controls, programmatic checkers)

## L2 Conditional Fusion Architecture

```
POST /v1/score
    │
    ├── L1: 12 statistical rules (p99 0.27 ms)
    │   └── BLOCK? → return immediately
    │
    ├── _run_l2_inference(request, txn)
    │   ├── l2_inference service loaded?  NO → MODEL_UNAVAILABLE
    │   ├── Ego graph extracted?          < 2 nodes → SKIPPED_NO_GRAPH
    │   ├── Inference > 40 ms?            YES → TIMEOUT
    │   ├── Exception?                    YES → ERROR
    │   └── All good                      → SUCCESS (prob > 0)
    │
    └── Ensemble fusion
        ├── L2 status == SUCCESS?  → full L1+L2 weighted fusion
        └── Otherwise              → L1-only fallback
```

This is a deliberate architectural choice: unconditionally blocking the hot path
on a synthetic-data-trained GNN would degrade availability for no fraud-detection
gain on fresh users. The five L2 status codes are surfaced in the API response
and tracked via Prometheus.

## Technical Debt Register

See [TECHNICAL_DEBT_REGISTER.md](TECHNICAL_DEBT_REGISTER.md). Key resolved items:
L2 conditional fusion (Phase 3), ensemble calibrator fitting ECE 0.055→0.010
(Phase 4), MFA/TOTP (Phase 9), per-key rate limits (Phase 9), async audit queue
(Phase 9), investigations pipeline batching (Phase 9).

Remaining: auto-model promotion needs manual approval gate, dashboard UI is
minimal, GNN uses synthetic data, agents tested in isolation (27 tests).

## Scalability Analysis

| Component | Bottleneck | Mitigation |
|-----------|-----------|------------|
| API | CPU (model inference) | Async Semaphore (20 concurrent batch jobs) |
| Redis | Memory bandwidth | Redis LRU (`allkeys-lru` enforced via `ensure_memory_policy`) |
| PostgreSQL | Connection pool | SQLAlchemy async engine + asyncpg |
| Celery | Redis throughput | Investigation queue is async, not hot-path |
| Ollama | CPU (~35 s/investigation) | Async — never blocks scoring |
