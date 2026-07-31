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

### Layer 2 — Heterogeneous GNN

- **Architecture**: 2-layer HeteroConv + SAGEConv (mean aggregation), hidden 64, global mean pooling readout + MLP, 53,826 params
- **Graph schema**: node types `user` (5) / `merchant` (19) / `device` (4) / `transaction` (4); edge types `performed`, `to`, `used`, `shared_by`, `transferred_to` (P2P)
- **Measured (synthetic, 2026-07-31)**: test PR-AUC 0.198 — the lead metric for imbalanced fraud (3.5× the edge-free MLP baseline 0.056); AUC-ROC 0.692, FPR 0.71 @ 90% recall; per-ego-graph inference p50 1.0 ms / p99 2.5 ms on CPU
- **vs. edge-free MLP baseline**: PR-AUC 0.056, AUC 0.48 — the per-relationship propagation of HeteroConv is worth the ~3.5× PR-AUC lift over ignoring graph structure
- **Provenance**: `scripts/benchmark_gnn.py` → `models/gnn_benchmark_results.json`; model card `models/payshield_gnn_v1_card.md`
- ⚠️ Not yet fused into the live `/v1/score` decision path (see README Limitations)

### Ensemble Fusion Engine
- Fuses L1 rule scores + GNN probability via weighted fusion
- Isotonic calibration for probability calibration
- Decision routing: ALLOW / BLOCK / REVIEW

### ML Engine
- Statistical pre-filter (L1) + GNN (L2) + ensemble fusion
- Model versioning and A/B testing via `models/registry`

### LLM Investigator
- Structured prompts for fraud analysis (JSON-only output contract)
- Transaction context enrichment
- Risk scoring with reasoning + quality scoring
- Ollama via Celery (async, off the scoring hot path) — qwen2.5:3b on CPU (~35 s)
- Tolerant parser: trailing commas, nested braces, key-value fallback

### Agent System
14 agent modules — 12 concrete agents + `MessageRouter` + `OrchestratorState`:

| Agent | Role |
|-------|------|
| `transaction_agent` | Analyzes a single transaction: features, rules, anomaly flags |
| `profile_agent` | Maintains user risk profiles from transaction history |
| `planner_agent` | Breaks complex investigations into ordered sub-tasks |
| `memory_agent` | Stores/retrieves investigation context across sessions |
| `human_review_agent` | Ingests analyst feedback into the decision loop |
| `reflection_agent` | Nightly FP clustering + drift detection + auto-tune recommendations |
| `critic_agent` | Challenges decisions, tracks challenge accuracy vs. feedback |
| `mitigation_agent` | Executes automated block/chill/rollback actions with confirmation |
| `collective_agent` | Coordinated multi-agent assessment (swarm voting, not a router) |
| `monitoring_agent` | Heartbeats, performance reports, agent health checks |
| `validation_agent` | Schema + rule validation on agent messages |
| `BaseAgent` | Abstract contract: config, message loop, error handling |

Stubs: `planner_agent` (only `COMPLEX_INVESTIGATION_REQUEST`), `collective_agent` (assessment + feedback, no live swarm consensus), `critic_agent` (accuracy tracking not wired to live scoring).

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
