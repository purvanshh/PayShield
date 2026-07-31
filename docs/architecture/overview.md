# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client Layer                         │
│  ┌─────────┐  ┌──────────┐  ┌───────────────────────┐  │
│  │ REST API│  │WebSocket │  │   React Dashboard     │  │
│  └────┬────┘  └────┬─────┘  └───────────┬───────────┘  │
└───────┼─────────────┼───────────────────┼──────────────┘
        │             │                   │
┌───────┴─────────────┴───────────────────┴──────────────┐
│                   API Gateway (FastAPI)                  │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ │
│  │  Auth    │ │Rate Limit│ │  Router   │ │Middleware│ │
│  └──────────┘ └──────────┘ └─────┬─────┘ └──────────┘ │
└──────────────────────────────────┼─────────────────────┘
                                   │
┌──────────────────────────────────┼─────────────────────┐
│           Core Engine            │                       │
│  ┌──────────┐  ┌────────────┐  ┌┴───────────┐         │
│  │  Feature  │  │  Ensemble  │  │     LLM    │         │
│  │ Pipeline  │  │  Fusion    │  │Investigator│         │
│  └────┬─────┘  └─────┬──────┘  └──────┬─────┘         │
│       │              │                │                 │
│  ┌────┴──────────────┴────────────────┴────┐           │
│  │        Agent Orchestrator (8 Agents)     │           │
│  └────────────────┬────────────────────────┘           │
└───────────────────┼────────────────────────────────────┘
                    │
┌───────────────────┼────────────────────────────────────┐
│     Async Layer   │                                     │
│  ┌────────────────┴──────────────┐                     │
│  │       Celery (RabbitMQ/Redis) │                      │
│  │  ┌────────┐ ┌───────────┐    │                      │
│  │  │Workers │ │   Beat    │    │                      │
│  │  └───┬────┘ └───────────┘    │                      │
│  └──────┼───────────────────────┘                      │
└─────────┼──────────────────────────────────────────────┘
          │
┌─────────┼──────────────────────────────────────────────┐
│  Data   │                                               │
│  ┌──────┴────────┐  ┌──────────────┐  ┌──────────┐   │
│  │  PostgreSQL   │  │    Redis     │  │    S3    │   │
│  │  (Transactions)│  │   (Cache)    │  │ (Models) │   │
│  └───────────────┘  └──────────────┘  └──────────┘   │
└────────────────────────────────────────────────────────┘
```

## Data Flow

### Transaction Processing Pipeline

```
Transaction → Feature Extraction (Redis-backed velocity/geo) → L1 Statistical Filter
                                                                ↓
                                                     Decision Gate
                                                    ┌───┴────────┐
                                                    │  BLOCK      │→ WebSocket alert
                                                    │ (rules)     │  + async investigation
                                                    └───┬────────┘
                                                        ↓ ALLOW/ESCALATE
                                                 GNN Inference (L2)
                                                        ↓
                                                 Ensemble Fusion
                                                        ↓
                                                 ALLOW / BLOCK / REVIEW
                                                        ↓
                              LLM Investigation (async, Celery + Ollama qwen2.5:3b)
                                                        ↓
                              Human Review / Feedback Loop (store/feedback/)
```

### Request Flow

1. **Client** sends transaction data via REST (`POST /v1/score`) or WebSocket
2. **API Gateway** authenticates (API key), rate-limits, routes
3. **Feature Pipeline** computes velocity/geo/Benford features live from Redis history
4. **Layer 1** evaluates 12 statistical rules (p99 0.27 ms)
5. **Layer 2 + Ensemble Fusion** produce the final ALLOW/BLOCK/REVIEW decision
6. **Persistence** on BLOCK/REVIEW: audit log entry (hash-chained), explanation artifact, drift sample
7. **LLM Investigator** (async) deep-dives blocked/reviewed transactions
8. **Response** returned to client — p50 8.5 ms, p90 15 ms measured (2026-07-31)

## Components

### API Layer
- FastAPI application with OpenAPI docs
- JWT-based authentication
- Rate limiting (token bucket)
- Request/response validation via Pydantic
- Prometheus metrics endpoint

### ML Engine
- 5 ensemble models + Gradient Boosting meta-learner
- Weighted voting fusion strategy
- Confidence-based decision routing
- Online learning from feedback
- Model versioning and A/B testing

### LLM Investigator
- Structured prompts for fraud analysis (JSON-only output contract)
- Transaction context enrichment
- Risk scoring with reasoning + quality scoring
- Ollama via Celery (async, off the scoring hot path) — qwen2.5:3b on CPU (~35 s)
- Tolerant parser: trailing commas, nested braces, key-value fallback

### Agent System
14 specialized agents (base, reflection, human review, mitigation, collective,
critic, validation, planner, profile, transaction, memory, monitoring, ...):
1. **Transaction Agent** - Core transaction analysis
2. **Risk Agent** - Risk scoring and aggregation
3. **Pattern Agent** - Pattern matching and anomaly detection
4. **Behavior Agent** - Behavioral analysis
5. **History Agent** - Historical context lookup
6. **Network Agent** - Network analysis (merchant, IP, device)
7. **Compliance Agent** - Regulatory checks
8. **Decision Agent** - Final decision synthesis
(+ reflection: FP clustering & drift; human review: feedback ingestion; mitigation; collective; critic; validation)

### Celery Tasks
- Transaction processing (high priority)
- LLM investigations (async)
- Model training/re-training (batch)
- Report generation (scheduled)
- Cache warming (scheduled)

## Security Architecture

- Network policies restrict pod-to-pod communication
- TLS termination at ingress
- JWT tokens with configurable expiry
- Sealed secrets for K8s secret management
- Read-only root filesystem for containers
- Non-root user execution
- CORS origin validation
- SQL injection protection (parameterized queries)

## Observability

- **Metrics**: Prometheus (API latency, error rates, queue depth, model confidence)
- **Logging**: Structured JSON logging (stdout → Loki)
- **Tracing**: OpenTelemetry for distributed tracing
- **Alerts**: Alertmanager (PagerDuty/Slack)
- **Dashboards**: Grafana (pre-built for each component)
- **Error Tracking**: Sentry integration
- **Drift**: PSI monitoring per feature (`drift:feat:*` zsets, rolling 24h windows; `GET /admin/drift/psi`) — robust estimator: shared quantile bins, bin-count scaling, Laplace smoothing

## Compliance

- **PCI-DSS**: 90/100 (passed) — AES-256 `ENCRYPTION_KEY`, RBAC enforced, hash-chained PII-masked audit log; MFA (8.3) deferred
- **RBI**: 100/100 (passed) — `DATA_REGION=IN`, explanation artifacts for every BLOCK/REVIEW, analyst feedback loop, versioned model cards
- Full before/after: `COMPLIANCE_DELTA.md`
