# PayShield — Real-Time UPI Fraud Detection Engine

**Multi-layer fraud scoring · Graph-powered investigation · 14-agent orchestration · Production-ready ops**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why PayShield

PayShield was built after I experienced a UPI fraud attempt firsthand. India's UPI network processes 18B+ transactions monthly; existing rule engines miss coordinated mule rings that only manifest as graph anomalies. This system demonstrates a production-grade 3-layer detection architecture: sub-millisecond statistical rules, graph neural networks for relational patterns, and LLM-generated investigation narratives — all with compliance, drift monitoring, and SRE tooling.

---

## Architecture

```
                    POST /v1/score
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ Velocity  │  │   Geo    │  │ Benford  │   ← Layer 1: Statistical Filter
    │ (6 rules) │  │(4 rules) │  │(2 rules) │      12 configurable rules
    └────┬──────┘  └────┬──────┘  └────┬──────┘
         └───────────────┼───────────────┘
                         ▼
                 ┌────────────────┐
                 │ Decision Gate  │──── BLOCK ──→ WebSocket Alert + Investigation
                 └───────┬────────┘
                         ▼ ALLOW/ESCALATE
                 ┌────────────────┐
                 │ GNN Inference  │   ← Layer 2: PyTorch Geometric
                 │ (Het. Graph)   │      Users, Merchants, Devices, Transactions
                 └───────┬────────┘
                         ▼
                 ┌────────────────┐
                 │ Ensemble Fusion│   ← Weighted fusion + Isotonic calibration
                 │  Engine        │
                 └───────┬────────┘
                         ▼ ALLOW/BLOCK/REVIEW
            ┌────────────────────────────┐
            │  LLM Investigation (async) │   ← Layer 3: Ollama + Celery worker
            │  Evidence · Narrative ·    │      qwen2.5:3b
            │  SHAP · Graph Context      │
            └───────────────┬────────────┘
                            ▼
            ┌────────────────────────────┐
            │  Reflection Agent          │   ← Feedback Loop
            │  FP clustering · Drift ·   │      Nightly weight sync
            │  Auto-recommendation       │      PostgreSQL + Redis
            └────────────────────────────┘
```

**Measured decision latency (2026-07-31, 50-request benchmark):**
`/v1/score` p50 8.5 ms · p90 15.0 ms · p99 63.3 ms. The tail is Redis feature reads + audit persistence; pure L1 rule evaluation is p99 0.27 ms (`latency_breakdown` in every response). LLM investigation runs **asynchronously** via Celery (qwen2.5:3b on CPU, ~35 s) — it never blocks scoring.

---

## Current Findings

Everything below is measured against the live stack (`docker compose`), not simulated.

### Fraud detection (Layer 1 rules, Redis-backed features)

| Scenario | Result |
|----------|--------|
| Normal single transaction (₹4.5k, new user) | ALLOW — ~1-3 ms |
| Velocity burst (12+ rapid transactions, ₹95k each) | BLOCK / REVIEW — `V-RULE-02` / `V-RULE-03` |
| Geo jump (Mumbai → Delhi in 20 min) | BLOCK — `G-RULE-01`, `G-RULE-02` |
| LLM investigation (qwen2.5:3b, async) | Valid JSON report — `MERCHANT_COLLUSION`, quality 1.0, served from `investigation:{txn_id}` |

### Layer 2 — Heterogeneous GNN (measured, `scripts/benchmark_gnn.py`)

Measured on 30k synthetic transactions (10k users, 1k merchants, 5% fraud, seed 42), user-disjoint 80/10/10 split, early-stopped training:

| Metric (test set) | GNN (HeteroConv+GraphSAGE) | Edge-free MLP baseline | Lift |
|-------------------|---------------------------|------------------------|------|
| **PR-AUC** (lead metric for imbalanced fraud) | **0.198** | 0.056 | **3.5×** |
| AUC-ROC | 0.692 | 0.481 | +0.21 |
| FPR @ 90% recall | 0.71 | 0.91 | −0.20 |
| Inference (CPU, per ego-graph) | p50 **1.0 ms** · p90 1.5 ms · p99 2.5 ms | — | — |
| Parameters | 53,826 | — | — |

**Why PR-AUC leads**: at fraud rates like 0.1%, AUC-ROC is dominated by correctly ranking the 99.9% legitimate majority — it can look high while the fraud class is missed. PR-AUC measures performance on the minority (fraud) class directly, so it's the honest number to lead with. The graph layer's value is the **3.5× PR-AUC lift** over an edge-free MLP, not the absolute 0.198 on synthetic data.

Graph schema (heterogeneous): **node types** `user` (5 feat: credit score, account age, KYC tier, txn frequency, device count), `merchant` (19 feat: 15 MCC one-hot + amount/refund/age/city), `device` (4 feat: OS, app version, emulator), `transaction` (4 feat: amount, hour, weekend, salary-day). **Edge types**: `performed` (user→txn), `to` (txn→merchant), `used` (user→device), `shared_by` (device→user), `transferred_to` (user→user, P2P).

Why HeteroConv + GraphSAGE instead of a simpler baseline? Each edge type gets its own SAGEConv weight matrix, so the model learns *per-relationship* propagation (shared-device mule rings ≠ merchant transfers) instead of collapsing the graph into one undirected adjacency — and the measured 3.5× PR-AUC lift above is the empirical justification: the edge-free MLP that ignores graph structure is barely better than a coin flip on this data. Full results: `models/gnn_benchmark_results.json`. Caveat: trained on synthetic data; the model card's earlier "AUC > 0.92" claim was never measured and is corrected to these numbers.

### Implementation Status

| Layer | Component | Status | Notes |
|-------|-----------|--------|-------|
| **L1** | Statistical filter (velocity, geo, Benford — 12 rules) | ✅ Production | p99 0.27 ms, Redis-backed features, config-driven rules |
| **L2** | Graph neural network (HeteroConv+SAGE) | 🟡 Conditional fusion | Runs live for returning users (`SUCCESS`, prob > 0); skips gracefully for fresh users with < 2 graph nodes (`SKIPPED_NO_GRAPH`). 40 ms timeout guard with L1 fallback on `TIMEOUT` / `ERROR` / `MODEL_UNAVAILABLE`. Benchmarked PR-AUC 0.198 (3.5× lift vs. edge-free MLP) |
| **L3** | LLM investigation (Celery + Ollama, async) | ✅ Production | qwen2.5:3b, ~35 s async, valid JSON reports with quality scores |
| **Ops** | Prometheus metrics + Grafana dashboards | ✅ Production | `prometheus/payshield-fraud-dashboard.json`, hot-path instrumentation |
| **Auth** | API keys + JWT refresh rotation + TOTP MFA | ✅ Production | Per-key/per-user rate limits (1000/hr), `/auth/totp` setup/verify |
| **Compliance** | PCI-DSS 90/100, RBI 100/100, EU AI Act checks | ✅ Production | Programmatic checkers with evidence collection; fairness SPD/EOD audit |
| **Audit** | Tamper-evident hash-chained JSONL + async queue | ✅ Production | PII masking, chain verification, <1ms hot-path append |

### Compliance (programmatic checkers — see `COMPLIANCE_DELTA.md`)

| Framework | Before | After | Status |
|-----------|--------|-------|--------|
| PCI-DSS | 60/100 | **90/100** | passed (no high-severity findings) |
| RBI | 16/100 | **100/100** | passed |
| EU AI Act | — | **100/100** | passed (risk mgmt, data gov, transparency, oversight, accuracy, robustness, conformity, post-market monitoring) |



### Drift detection (PSI, rolling 24h windows)

`GET /admin/drift/psi` (or `python scripts/run_drift_report.py`):

```
  txn_count_5m               PSI=0.0123  STABLE
  txn_count_1h               PSI=0.0123  STABLE
  amount_total_1h            PSI=3.8608  DRIFT   ← hourly amount aggregate shifted ~33%
  device_txn_count_24h       PSI=0.0089  STABLE
  distinct_users_last_24h    PSI=0.0000  STABLE
  distinct_merchants_1h      PSI=0.0000  STABLE
```

The `amount_total_1h` drift was investigated: today's hourly aggregate (₹2.66-3.32M) vs yesterday's baseline (₹3.99-4.99M) — consistent with the seeded burst scenario. Methodology: shared quantile bins on the combined distribution, bin count scaled to sample size, Laplace smoothing (see [Bug Resolution](#bug-resolution-and-technical-notes) for the estimator fix).

---

## Bug Resolution and Technical Notes

Notable issues found and fixed while bringing the stack up end-to-end:

| # | Bug | Root cause | Fix |
|---|-----|------------|-----|
| 1 | API crash at startup | `StatisticalFilter` called `config.get(...)` on `None` | use `self.config.get(...)` |
| 2 | Score route returned canned results | features were never computed | real Redis-backed velocity/geo features (`velocity:user:`, `velocity:dev:`, `velocity:loc:`) |
| 3 | Redis/Ollama connections used `localhost` inside containers | hardcoded defaults | env-driven `REDIS_HOST`/`OLLAMA_BASE_URL`/`OLLAMA_MODEL` |
| 4 | Worker died at boot: `No module named 'infrastructure'` | fork-time import of bridge module | module-level import with fallback (`store.sync_redis`) |
| 5 | Investigation route 500 on reports | worker stored nested `{status, report}` | accept flat or nested report dicts |
| 6 | LLM returned unparseable output | JSON embedded in prose | JSON-only prompt + tolerant parser (trailing commas, key-value fallback) |
| 7 | `UnboundLocalError: l2` in evidence collection | `l2` referenced before assignment | initialize `l1`/`l2` before use |
| 8 | Investigation never ran | wrong Celery app module + no task `include` | `celery -A tasks.celery_app`, explicit task list |
| 9 | RBAC 403 on investigations | `system` role lacked `investigation:read` | add to `configs/rbac.yaml` |
| 10 | Role endpoints rejected valid API keys | `get_current_user` only read Bearer header | accept `x-api-key` fallback |
| 11 | Dashboard Docker build failed | missing deps, TS errors, wrong COPY paths | add `react-router-dom`/`axios`/`zustand`, fix Dockerfile + types |
| 12 | Compliance findings persisted nowhere | audit log did not exist | `store/audit_log.py` (hash-chained JSONL + PII masking) — see `COMPLIANCE_DELTA.md` |
| 13 | **Drift report showed PSI=43.4** | PSI estimator: 10 fixed bins on 14 discrete samples, zero-mass bins, no smoothing, `density=True` double normalization | shared quantile edges, bin count `max(3, n//5)`, Laplace smoothing — validated: identical→0.000, 1σ→0.981, real case 43.4→**3.86** |
| 14 | Drift samples never recorded | missing `await` on `_record_drift_samples` | awaited; also fixed zset member/score convention mismatch |
| 15 | Container rebuilds wiped audit/explanation artifacts | code dirs shadowed by volumes | named volumes on leaf data dirs (`store/audit_logs`, `store/feedback`, `models/production/explanations`, `compliance/reports`) |
| 16 | Synthetic generator crashed: `Cannot choose from an empty sequence` | `CITY_TIER_WEIGHTS` samples `tier4` but `INDIAN_CITIES` had no tier-4 cities | added 4 tier-4 cities (Agra, Varanasi, Kochi, Gwalior) |
| 17 | Synthetic generator crashed on device generation | `random.choice` called with `weights=` kwarg (numpy API on stdlib RNG) | `rng.choices(..., weights=[...])[0]` |
| 18 | GNN benchmark revealed the model card's `AUC > 0.92` was never measured | aspirational claim from the design phase | corrected to measured test PR-AUC 0.198 (3.5× vs edge-free MLP 0.056) + AUC-ROC 0.692 (`scripts/benchmark_gnn.py`, `models/gnn_benchmark_results.json`); also fixed L2 claims: params 53,826 (not ~15K), CPU latency p99 2.5 ms (not < 50 ms) |

---

## Agent System

14 agent modules — 12 concrete agents plus `MessageRouter` and `OrchestratorState` infrastructure. All 12 process messages via `BaseAgent.process`; the feedback-driven ones (reflection, critic, human review) are exercised end-to-end by the live stack.

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

Stubs: `planner_agent` handles only `COMPLEX_INVESTIGATION_REQUEST`; `collective_agent` implements assessment + feedback (no live swarm consensus yet); `critic_agent` tracks accuracy but isn't wired to the live scoring path. Everything else runs in the demo flow.

---

## Limitations & Deferred Work

Honest accounting of what this system does not do yet:

- **MFA**: TOTP implemented in P9 — admin setup/verify endpoint with 30s rolling codes (RFC 6238, SHA-1).
- **GNN on CPU**: L2 is CPU-bound; a GPU would cut the already-sub-2.5ms inference further and speed up retraining.
- **Real UPI volume**: everything is tested on synthetic data; real NPCI traffic has different seasonality and mule-ring density.
- **GNN accuracy**: measured test PR-AUC 0.198 (3.5× vs. edge-free MLP baseline 0.056), AUC-ROC 0.692 on synthetic ego-graphs — the relational lift over an edge-free MLP is real and consistent, but the absolute numbers are modest; improvement paths: per-node readout instead of graph-level pooling, more history, real data.
- **Model retraining**: auto-trigger exists (reflection task) but the manual approval gate for promotion is not wired — `POST /admin/models/promote` is the manual step.
- **LLM on CPU**: ~35 s per investigation is fine async, but GPU (or an API fallback) would enable real-time investigation.
- **L2 conditional fusion**: GNN runs live for returning users (`SUCCESS`, prob > 0) and skips gracefully for fresh users with < 2 graph nodes (`SKIPPED_NO_GRAPH`), with a 40 ms timeout guard. It is not a blocking hard gate — the ensemble falls back to L1-only fusion on `TIMEOUT`, `ERROR`, or `MODEL_UNAVAILABLE`. This is a deliberate architectural choice: unconditionally blocking the hot path on a synthetic-data-trained GNN would degrade availability for no fraud-detection gain on fresh users.

---

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local development)

### Docker Compose (One Command)

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up
```

This starts 5 services:

| Service | Port | Role |
|---------|------|------|
| **api** | `8000` | FastAPI application (uvicorn) |
| **worker** | — | Celery worker (async investigations) |
| **redis** | `6379` | Cache + Celery broker/backend |
| **ollama** | `11434` | Local LLM inference |
| **dashboard** | `3000` | Vite + React frontend |

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for testing/linting

# 2. Configure environment
cp .env.example .env

# 3. Start external services
redis-server &
ollama serve && ollama pull qwen2.5:3b &

# 4. Bootstrap data stores
python scripts/init_db.py
python scripts/seed_redis.py

# 5. Start API
uvicorn api.main:app --reload --port 8000

# 6. Start Celery worker (separate terminal)
celery -A tasks.celery_app worker -Q investigation,default --loglevel=info
```

### Verify

```bash
# Health check
curl http://localhost:8000/health

# Score a transaction
curl -X POST http://localhost:8000/v1/score \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "txn_id": "TEST001",
    "user_id": "U001",
    "merchant_id": "M001",
    "amount": 500.0,
    "timestamp": "2026-07-29T12:00:00",
    "device_fingerprint": "DEV001",
    "location": {"lat": 19.0760, "lon": 72.8777},
    "mcc_code": "food",
    "txn_type": "P2M"
  }'
```

API docs: `http://localhost:8000/docs` (Swagger) · `http://localhost:8000/redoc` (ReDoc)

---

## API Reference

### Fraud Scoring
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/score` | API Key | Score a single transaction |
| `POST` | `/v1/batch` | API Key + RBAC | Score up to 100 transactions |

### Investigation
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/investigation/{txn_id}` | API Key | Get LLM investigation report |
| `GET` | `/v1/investigations` | API Key + RBAC | List investigations (paginated) |

### Feedback Loop
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/feedback` | API Key + RBAC | Submit analyst decision (persisted to `store/feedback/`) |
| `GET` | `/v1/feedback/stats` | API Key + RBAC | Feedback volume by category |

### Graph Analysis
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/graph/investigate` | API Key | Investigate entity in fraud graph |
| `GET` | `/v1/graph/network/{entity_id}` | API Key | Get entity ego-graph |
| `POST` | `/v1/graph/entity` | API Key | Create graph entity |
| `POST` | `/v1/graph/link` | API Key | Link two entities |
| `GET` | `/v1/graph/risk-paths` | API Key | Find risk paths between entities |
| `GET` | `/v1/graph/stats` | API Key | Graph DB statistics |

### Compliance & Sanctions
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/admin/compliance/status` | API Key | PCI-DSS, RBI, EU AI Act scores |
| `GET` | `/admin/compliance/check/{user_id}` | API Key | Sanctions + KYC combined check |
| `POST` | `/admin/compliance/sanctions/check` | API Key | OFAC/UN sanctions screening |
| `GET` | `/admin/compliance/kyc/{user_id}` | API Key | KYC tier verification |
| `POST` | `/admin/compliance/aml/check` | API Key | AML velocity + structuring check |
| `POST` | `/admin/compliance/report` | API Key | Generate quarterly compliance report |
| `POST` | `/admin/compliance/report/{framework}` | API Key | Framework-specific report |
| `GET` | `/admin/compliance/evidence` | API Key | List compliance evidence archives |
| `POST` | `/admin/compliance/evidence/collect` | API Key | Trigger evidence collection |

### Admin & Operations
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/rules/reload` | API Key + RBAC | Reload statistical rules from YAML |
| `POST` | `/admin/models/promote` | API Key + RBAC | Promote model version |
| `POST` | `/admin/config/threshold` | API Key + RBAC | Update scoring threshold |
| `GET` | `/admin/config` | API Key + RBAC | View all configurations |
| `GET` | `/admin/agents/health` | API Key + RBAC | Multi-agent health status |
| `POST` | `/admin/agents/{id}/restart` | API Key + RBAC | Restart a specific agent |
| `GET` | `/admin/drift/psi` | API Key + RBAC | PSI drift report (yesterday vs today) |

### A/B Experiments
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/experiments` | API Key | Register new A/B experiment |
| `GET` | `/admin/experiments` | API Key | List all experiments |
| `GET` | `/admin/experiments/{id}/results` | API Key | Get experiment results + p-value |
| `POST` | `/admin/experiments/{id}/promote` | API Key | Promote challenger model |
| `POST` | `/admin/experiments/{id}/rollback` | API Key | Rollback to champion |

### Real-Time Streams
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `WS` | `/v1/stream` | Token/Key | WebSocket for live fraud alerts |
| `GET` | `/v1/stream/sse` | Token | Server-Sent Events stream |

### Operations
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Full health (Redis, Neo4j, Ollama, Celery) |
| `GET` | `/health/live` | None | Kubernetes liveness probe |
| `GET` | `/health/ready` | None | Kubernetes readiness probe |
| `GET` | `/metrics` | None | Prometheus metrics |

---

## Project Structure

```
PayShield/
├── api/                       # FastAPI application (12 files, 11 routes)
│   ├── routes/                # health, score, investigation, feedback, graph,
│   │                          #   compliance, admin, experiments, stream, metrics
│   ├── main.py                # App factory + middleware wiring
│   ├── schemas.py             # Pydantic request/response models
│   ├── dependencies.py        # DI: Redis, ensemble, auth
│   ├── exceptions.py          # Typed exception hierarchy
│   ├── middleware.py           # Correlation ID, timing, security headers
│   ├── websocket.py           # WebSocket manager + AlertBroadcaster
│   └── lifespan.py            # Startup/shutdown resource lifecycle
│
├── engine/                    # Scoring & decision engine (10 files)
│   ├── statistical_filter.py  # L1: Velocity (6), Geo (4), Benford (2) rules
│   ├── ensemble.py            # L2+: Fusion engine, isotonic calibrator
│   ├── graph_model.py         # PyTorch Geometric GNN
│   ├── graph_feature_engine.py/# Graph feature extraction
│   ├── graph_builder.py       # Heterogeneous graph construction
│   ├── graph_loader.py        # Graph data loading
│   └── explainer.py           # GNNExplainer + SHAP bridge
│
├── agents/                    # Multi-agent framework (15 files, 14 agents)
│   ├── base.py                # AgentConfig, MessageRouter, AgentState
│   ├── reflection_agent.py    # FP clustering, drift detection, auto-tune
│   ├── human_review_agent.py  # Human-in-the-loop feedback ingestion
│   ├── mitigation_agent.py    # Automated mitigation actions
│   ├── collective_agent.py    # Agent swarm coordinator
│   ├── critic_agent.py        # Decision quality evaluation
│   ├── validation_agent.py    # Schema + rule validation
│   └── ...                    # planner, profile, transaction, memory, monitoring
│
├── llm/                       # Ollama LLM integration (14 files)
│   ├── client.py              # Async + sync Ollama API client
│   ├── config.py              # OllamaConfig (model, timeout, retries)
│   ├── evidence.py            # Evidence collection from L1/L2 results
│   ├── parser.py              # LLM output → InvestigationReport
│   ├── prompt_builder.py      # Structured prompts for fraud detection
│   ├── investigator.py        # End-to-end investigation orchestration
│   └── prompts/               # Prompt templates + examples
│
├── compliance/                # Regulatory compliance (9 files)
│   ├── pci_dss.py             # PCI-DSS: 10 controls, log scanning
│   ├── rbi_localization.py    # RBI: data residency, explainability, oversight
│   ├── eu_ai_act.py           # EU AI Act: risk mgmt, transparency, robustness
│   ├── sanctions.py           # Sanctions (OFAC/UN), AML engine, KYC verifier
│   ├── audit_generator.py     # Quarterly compliance report generation
│   └── evidence_collector.py  # Tamper-proof evidence archives
│
├── data/                      # Data generation & features (16 files)
│   ├── synthetic/             # UPI transaction generator (realistic fraud patterns)
│   ├── features/              # Benford's Law, geospatial, velocity
│   └── validation/            # Data quality validator (Great Expectations)
│
├── store/                     # Data stores (17 files)
│   ├── redis_client.py        # AsyncRedisClient w/ circuit breaker
│   ├── sync_redis.py          # SyncRedisClient (Celery workers)
│   ├── audit_log.py           # Tamper-evident audit log (hash chain + PII masking)
│   ├── neo4j_client.py        # Neo4j client: users, merchants, devices, transactions
│   ├── graph_db.py            # NetworkX fallback graph DB
│   ├── postgres.py            # SQLAlchemy async engine + session
│   ├── models.py              # SQLAlchemy ORM models (9 tables)
│   ├── feature_store.py       # Redis-backed feature store
│   └── connection_pool.py     # Redis pool w/ circuit breaker + fallback cache
│
├── tasks/                     # Celery tasks (9 files)
│   ├── celery_app.py          # Celery config + beat schedule
│   ├── investigation_task.py  # Async LLM investigation
│   ├── reflection_task.py     # Nightly reflection + weight sync
│   └── compliance_task.py     # Scheduled PCI/RBI/EU checks
│
├── ml/                        # ML lifecycle (8 files)
│   ├── train.py               # GNN model training
│   ├── registry.py            # Model version registry
│   ├── ab_testing.py          # Champion/challenger A/B framework
│   └── continuous_improvement.py /# Auto-retraining triggers
│
├── observability/             # Monitoring (5 files)
│   ├── logging_config.py      # Structured logging (structlog)
│   ├── drift.py               # Robust PSI (shared quantile bins, Laplace smoothing)
│   ├── drift_report.py        # Yesterday-vs-today PSI report (async-safe, both clients)
│   └── metrics.py             # Prometheus metrics
│
├── infrastructure/            # Cross-cutting (1 file)
│   └── redis_bridge.py        # Async/sync Redis client factory
│
├── configs/                   # YAML configuration (7 files)
│   ├── config.yaml            # Main app config
│   ├── statistical_rules.yaml # L1 rule definitions
│   ├── feature_registry.yaml  # Feature definitions
│   ├── rbac.yaml              # Role-based access control
│   ├── model_schema.yaml      # ML model schema
│   └── thresholds/            # Environment-specific thresholds (dev + prod)
│
├── models/                    # Model registry + cards
│   ├── registry/              # v1.0.0 (statistical filter) + v0.1.0 (GNN) model cards
│   └── payshield_gnn_v1_card.md
├── dashboard/                 # Vite + React + TypeScript frontend
├── docker/                    # Dockerfiles + Compose (5 services, named data volumes)
├── k8s/                       # Kubernetes manifests (base + dev/staging/prod overlays)
│   └── base/                  # 16 manifests: deployments, HPA, ingress, network
│                              #   policies, PDBs, sealed secrets, postgres, redis,
│                              #   celery, backup cronjobs, kustomization
├── sre/                       # SRE toolkit
│   ├── slos/                  # SLO definitions (dashboard, scoring, investigation)
│   ├── runbooks/              # Incident response + escalation
│   ├── error-budgets/         # Error budget tracking
│   ├── chaos/                 # 5 chaos experiments (api, neo4j, ollama, pg, redis)
│   └── dashboards/            # Grafana dashboard JSON
├── dr/                        # Disaster recovery (9 scripts)
│   ├── backup-postgres.sh     # Automated PostgreSQL backup
│   ├── backup-redis.sh        # Redis RDB backup
│   ├── restore-*.sh           # Restore procedures
│   └── DR_RUNBOOK.md          # Recovery runbook
├── alembic/                   # PostgreSQL migrations
├── docs/                      # Technical documentation (architecture, guides, ops)
├── notebooks/                 # Jupyter notebooks (EDA, fraud patterns, model ablation)
├── scripts/                   # 43 utility scripts (benchmarks, training, data ops)
├── tests/                     # Test suite
│   ├── unit/                  # 13 unit test files
│   ├── integration/           # API + graph integration tests
│   ├── e2e/                   # End-to-end pipeline tests
│   └── load/                  # Locust load tests
├── Makefile                   # 30+ targets (test, lint, train, deploy, chaos)
├── pyproject.toml             # Build config + tool settings
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Dev + test dependencies
└── .env.example               # All environment variables documented
```

---

## Data Stores

| Store | Driver | Purpose |
|-------|--------|---------|
| **PostgreSQL** | SQLAlchemy + asyncpg | Primary: users, audit logs, feedback, investigations, API keys |
| **Neo4j** | `neo4j.AsyncGraphDatabase` | Fraud graph: entities, relationships, risk paths, network scoring |
| **Redis** | `redis.asyncio` + `redis` | Cache, rate limiting, Celery broker/backend, feature store, idempotency |

---

## AI / ML Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **L1: Statistical** | scipy, sklearn | Rule-based: velocity, geo-velocity, Benford's Law (12 rules) |
| **L2: GNN** | PyTorch Geometric | Heterogeneous graph neural network (User/Merchant/Device/Transaction) |
| **Fusion** | Custom + Isotonic | Weighted fusion with calibrated confidence scores |
| **L3: LLM** | Ollama (qwen2.5:3b) | Natural language investigation reports (async via Celery) |
| **Explainability** | SHAP + GNNExplainer | Feature importance, evidence subgraphs |
| **Feedback** | Reflection Agent | FP clustering, drift detection, nightly weight auto-tuning |
| **A/B Testing** | Custom framework | Champion/challenger experiments with statistical significance |
| **Drift** | PSI (robust) | Feature distribution monitoring, rolling 24h windows |

---

## Model Training

Model artifacts (`.pkl`, `.onnx`, `.pt`) are generated by the training pipeline:

```bash
# Generate synthetic training data
make generate-data

# Train the GNN model
make train

# Evaluate on validation set
make evaluate

# Promote to production (via admin API)
curl -X POST http://localhost:8000/admin/models/promote \
  -H "X-API-Key: payshield-dev-key-2026" \
  -d '{"version": "v1.1.0", "stage": "production"}'
```

See `models/README.md` for artifact conventions.

---

## Dashboard

The frontend is a **Vite + React + TypeScript** application under active development:

```bash
cd dashboard
npm install
npm run dev          # → http://localhost:5173
```

Pages: Login, Dashboard (fraud gauge, transaction table, alert toast), Investigation Detail (graph visualization). Connects via:
- `VITE_API_URL` (default: `http://localhost:8000`)
- `VITE_WS_URL` (default: `ws://localhost:8000`)

---

## CI / CD

| Stage | Tool |
|-------|------|
| **Lint** | `ruff check .` |
| **Format** | `ruff format .` |
| **Type check** | `mypy api/ engine/ agents/` |
| **Tests** | `pytest --cov --cov-report=term-missing` |
| **Security scan** | `bandit -r .` |
| **Coverage target** | 70% |
| **Deployment** | ArgoCD → Kubernetes (`k8s/overlays/prod`) |

```bash
make ci           # Runs: lint → test → typecheck
make test         # All tests
make test-unit    # Unit only
make lint         # Ruff check
make format       # Ruff format
make security-scan/# Bandit audit
```

---

## Operations

```bash
make up           # Start all services (Docker)
make down         # Stop all services
make build        # Rebuild images
make logs         # Tail all service logs
make shell-api    # Shell into API container
make shell-worker # Shell into worker container
```

### Chaos Engineering
```bash
make chaos-run    # Run a specific chaos experiment
make chaos-test   # Run all chaos experiments
```

### Compliance Checks
```bash
make compliance-check   # Run all compliance checkers
make compliance-report  # Generate quarterly report
```
Current scores (see `COMPLIANCE_DELTA.md` for the full before/after): **PCI-DSS 90/100** (passed), **RBI 100/100** (passed).

### Drift Monitoring
```bash
# Manual PSI report (yesterday vs today feature distributions)
python scripts/run_drift_report.py

# Or via API (same computation, async-safe)
curl http://localhost:8000/admin/drift/psi -H "X-API-Key: payshield-dev-key-2026"

# Seed a baseline replay into yesterday's window (demo/lab)
python scripts/seed_drift_baseline.py

# Latency benchmark (sync scoring path)
python scripts/benchmark_latency.py
```

### Disaster Recovery
```bash
./dr/backup-postgres.sh    # Backup PostgreSQL
./dr/backup-redis.sh       # Backup Redis
./dr/restore-postgres.sh   # Restore PostgreSQL
./dr/restore-redis.sh      # Restore Redis
./dr/test-restore.sh       # Validate restore integrity
```

---

## Environment Variables

All configurable via `.env.example`:

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `PAYSHIELD_DEV_API_KEY` | `payshield-dev-key-2026` | Dev | API authentication |
| `JWT_SECRET` | `payshield-jwt-secret-dev-2026` | Prod | JWT signing |
| `REDIS_HOST` / `REDIS_PORT` | `localhost:6379` | Yes | Redis connection |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Yes | PostgreSQL connection |
| `NEO4J_URI` | `bolt://localhost:7687` | Yes | Neo4j connection |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Yes | LLM inference |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Yes | LLM model name |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Yes | Task queue |
| `ENCRYPTION_KEY` | `pay-shield-dev-aes256-key-0001` | PCI-DSS | AES-256 key for data at rest (dev-only default) |
| `ENFORCE_RBAC` | `false` | PCI-DSS | RBAC on admin endpoints (compose sets `true`) |
| `DATA_REGION` | `IN` | RBI | Data residency (India) |
| `ENABLE_LLM_INVESTIGATOR` | `true` | RBI | LLM explanation narratives |
| `ENABLE_HUMAN_REVIEW` | `true` | EU AI Act | Human oversight |
| `MFA_ENABLED` | `false` | PCI-DSS | MFA for admin accounts (deferred — see `COMPLIANCE_DELTA.md`) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Quick checklist:

1. Create a feature branch
2. Run `make lint` and fix issues
3. Run `make test` — all tests must pass
4. Add tests for new functionality
5. Run `make typecheck`
6. Update `.env.example` for new env vars
7. Never commit secrets or API keys

Pre-commit hooks are configured in `.pre-commit-config.yaml` (ruff, mypy, bandit).

---

## License

MIT — see [LICENSE](LICENSE)
