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

## Track 2 — AI Risk Manager

- [Track 2 Architecture](TRACK2_ARCHITECTURE.md) — the three-act risk suite
- [API Reference (Track 2)](API_REFERENCE.md) — every new endpoint with schemas/errors
- [Design Decisions](DESIGN_DECISIONS.md) — the "why" behind the choices
- [Demo Script](DEMO_SCRIPT.md) · [Demo Data](DEMO_DATA.md) — verified walkthrough
- [Judge Q&A](JUDGE_QA.md) · [Panel Prep](PANEL_PREP.md) — rehearsed answers
- [Live Panel Demo](LIVE_PANEL_DEMO.md)
- [Security Audit](SECURITY_AUDIT.md) · [Load Testing](LOAD_TESTING.md) ·
  [Performance](PERFORMANCE_OPTIMIZATION.md)
- [Chaos Engineering](CHAOS_ENGINEERING.md) · [A/B Testing](AB_TESTING.md) ·
  [Drift Monitoring](DRIFT_MONITORING.md)
- [Troubleshooting](TROUBLESHOOTING.md) · [Submission Checklist](SUBMISSION_CHECKLIST.md)

## System Overview

PayShield processes real-time UPI transactions through a three-layer pipeline:

1. **L1 Statistical Filter** — 12 configurable rules (velocity, geo, Benford) with Redis-backed features. p99 0.27 ms.
2. **L2 GNN (Conditional Fusion)** — HeteroConv+SAGEConv graph neural network. Runs for returning users (≥ 2 graph nodes), skips for fresh users, 40 ms timeout guard. 5 status codes.
3. **L3 LLM Investigation (Async)** — Celery + Ollama qwen2.5:3b. JSON-only prompt, tolerant parser. ~35 s async — never blocks scoring.

## Key Features

- Real-time fraud detection (p50 8.5 ms, p99 63.3 ms measured)
- L2 GNN v1.1.0 conditional fusion: 4.0× PR-AUC lift vs edge-free MLP baseline; PR-AUC 0.4125 (+108% vs v1.0.0)
- Ensemble fusion with isotonic calibration (ECE 0.010)
- 14-agent framework (12 concrete agents + router + state)
- JWT authentication + refresh rotation + TOTP MFA
- Per-API-key/per-user rate limiting (Redis incr+TTL)
- Tamper-evident hash-chained audit log with async queue (<1ms append)
- Prometheus/Grafana observability (4-panel dashboard, 5 alert rules)
- PSI drift detection driven by the feature registry (monitoring: true entries, drift_key aliases, binary-aware binning)
- Automated retrain + improvement gate (`make retrain`, epsilon 0.005 PR-AUC, weekly CI workflow)
- 573 tests (hermetic; no external services required)

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
