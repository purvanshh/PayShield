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

- **Architecture**: 3-layer HeteroConv + SAGEConv (mean aggregation), hidden 128, dropout 0.3, target-user readout with transaction attention + MLP head, 371,843 params
- **Graph schema**: node types `user` (5) / `merchant` (21) / `device` (4) / `transaction` (8); edge types `performed`, `to`, `used`, `shared_by`, `transferred_to` (P2P)
- **Measured (synthetic, 2026-08-15, model v1.1.0)**: test PR-AUC 0.4125 — the lead metric for imbalanced fraud (4.0× the edge-free MLP baseline 0.1028, +108% vs v1.0.0's 0.198); AUC-ROC 0.7668, FPR 0.49 @ 90% recall; per-ego-graph inference p50 0.60 ms / p99 0.70 ms on CPU
- **vs. edge-free MLP baseline**: PR-AUC 0.1028, AUC-ROC 0.5395 — the per-relationship propagation of HeteroConv is worth the ~4.0× PR-AUC lift over ignoring graph structure
- **Live features**: velocity (inter-arrival gap, txn counts 5m/1h), geo (haversine distance from the user's last known location), and merchant round-amount share are computed on the scoring path, cached in Redis (`FeatureCache`), and written onto graph nodes by `GraphDBWriter` so the feature engine reads them back at inference
- **Checkpoint-driven serving**: `ml/inference.py` reconstructs the model from the checkpoint's own `hidden_channels`/`num_layers`/`dropout` metadata (no hardcoded architecture); target-user index read from `data.target_txn_n`
- **Provenance**: `scripts/benchmark_gnn.py` → `models/gnn_benchmark_results.json`; delta vs. archived original: `models/gnn_benchmark_delta.md`; model card `models/payshield_gnn_v1_card.md`, versioned under `models/registry/v1.1.0/` (`models/registry/latest` → v1.1.0)
- ✅ Conditionally fused — runs live for returning users (`SUCCESS`, prob > 0); skips for fresh users with < 2 graph nodes (`SKIPPED_NO_GRAPH`). 40 ms timeout guard with L1 fallback on TIMEOUT / ERROR / MODEL_UNAVAILABLE.

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
- JWT tokens with 7-day sliding refresh rotation (HS256)
- TOTP MFA for admin accounts (RFC 6238, SHA-1, 30s step, pure stdlib)
- API Key authentication (SHA-256 hashed)
- Per-API-key rate limiting (1000 req/hr, Redis incr+TTL) + per-user limits
- Sealed secrets for K8s secret management
- Read-only root filesystem for containers
- Non-root user execution
- CORS origin validation (env-driven `FRONTEND_URL`, no wildcard)
- SQL injection protection (parameterized queries)

## Observability

- **Metrics**: Prometheus (API latency, error rates, queue depth, model confidence)
- **Logging**: Structured JSON logging (stdout → Loki)
- **Tracing**: Correlation IDs via `CorrelationIdMiddleware` (logged on every request)
- **Alerts**: `prometheus/alerts.yml` (5 rules)
- **Dashboards**: Grafana — `payshield-fraud-dashboard.json` (4 panels)
- **Drift**: PSI monitoring per feature (`drift:feat:*` zsets, rolling 24h windows; `GET /admin/drift/psi`) — robust estimator: shared quantile bins, bin-count scaling, Laplace smoothing, exact-value binning for binary/categorical features. The monitored feature set is driven by the global feature registry (`configs/feature_registry.yaml`, entries with `monitoring: true`, `drift_key` aliases to the recorded zset); `skew_detection` sets the PSI threshold and `min_samples` floor

## Compliance

- **PCI-DSS**: 90/100 (passed) — AES-256 `ENCRYPTION_KEY`, RBAC enforced, hash-chained PII-masked audit log; MFA resolved (P9 TOTP)
- **RBI**: 100/100 (passed) — `DATA_REGION=IN`, explanation artifacts for every BLOCK/REVIEW, analyst feedback loop, versioned model cards
- **EU AI Act**: 100/100 (passed) — 13 controls including conformity assessment, post-market monitoring, human oversight logging, fairness audit (SPD/EOD)
- Full before/after: `COMPLIANCE_DELTA.md`
