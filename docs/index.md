# PayShield Documentation

Real-time UPI fraud detection with three-layer scoring: L1 statistical filter
(sub-millisecond rules), L2 graph neural network (conditional fusion), and L3
async LLM investigation (Celery + Ollama).

## Quick Links

- [Getting Started Guide](guides/getting-started.md)
- [Architecture Overview](architecture/overview.md)
- [Ensemble Architecture](architecture/ensemble.md)
- [API Reference](api/endpoints.md)
- [Operations Manual](operations/deployment.md)
- [Monitoring Guide](operations/monitoring.md)
- [Troubleshooting Guide](operations/troubleshooting.md)
- [ML Training Guide](training/ml-guide.md)
- [Changelog](reference/changelog.md)
- [FAQ](reference/faq.md)

## System Overview

PayShield processes real-time UPI transactions through a three-layer pipeline:

1. **L1 Statistical Filter** — 12 configurable rules (velocity, geo, Benford) with Redis-backed features. p99 0.27 ms.
2. **L2 GNN (Conditional Fusion)** — HeteroConv+SAGEConv graph neural network. Runs for returning users (≥ 2 graph nodes), skips for fresh users, 40 ms timeout guard. 5 status codes.
3. **L3 LLM Investigation (Async)** — Celery + Ollama qwen2.5:3b. JSON-only prompt, tolerant parser. ~35 s async — never blocks scoring.

## Key Features

- Real-time fraud detection (p50 8.5 ms, p99 63.3 ms measured)
- L2 GNN conditional fusion: 3.5× PR-AUC lift vs edge-free MLP baseline
- Ensemble fusion with isotonic calibration (ECE 0.010)
- 14-agent framework (12 concrete agents + router + state)
- JWT authentication + refresh rotation + TOTP MFA
- Per-API-key/per-user rate limiting (Redis incr+TTL)
- Tamper-evident hash-chained audit log with async queue (<1ms append)
- Prometheus/Grafana observability (4-panel dashboard, 5 alert rules)
- PSI drift detection (robust estimator: shared quantile bins + Laplace smoothing)
- 392 tests at 74% coverage (gates: score 91%, ensemble 90%, graph 99%)

## Tech Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI (Python 3.11+) |
| ML | PyTorch Geometric (HeteroConv + SAGEConv) |
| LLM | Ollama (qwen2.5:3b) |
| Queue | Celery + Redis |
| Database | PostgreSQL 16 + Redis 7 |
| Streaming | WebSocket + SSE |
| Infra | Docker, Kubernetes, ArgoCD |
| Monitoring | Prometheus, Grafana |
| Auth | JWT (HS256) + TOTP MFA (RFC 6238) |

## Project Documents

- [STUDY_GUIDE.md](../STUDY_GUIDE.md) — Interview preparation and codebase walkthrough
- [AUDIT_REPORT_v2.md](../AUDIT_REPORT_v2.md) — Post-Phase-10 audit findings triage
- [COMPLIANCE_DELTA.md](../COMPLIANCE_DELTA.md) — Before/after compliance scores
- [TECHNICAL_DEBT_REGISTER.md](../TECHNICAL_DEBT_REGISTER.md) — Active and resolved debt items
- [ARCHITECTURE_REVIEW.md](../ARCHITECTURE_REVIEW.md) — Architecture review v2
- [PERFORMANCE_OPTIMIZATION_LOG.md](../PERFORMANCE_OPTIMIZATION_LOG.md) — Latency optimization log
