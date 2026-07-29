# PayShield — Real-Time UPI Fraud Detection Engine

**Multi-layer fraud scoring · Graph-powered investigation · 14-agent orchestration · Production-ready ops**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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
            │  Evidence · Narrative ·    │      llama3.1:8b
            │  SHAP · Graph Context      │
            └───────────────┬────────────┘
                            ▼
            ┌────────────────────────────┐
            │  Reflection Agent          │   ← Feedback Loop
            │  FP clustering · Drift ·   │      Nightly weight sync
            │  Auto-recommendation       │      PostgreSQL + Redis
            └────────────────────────────┘
```

**Decision latency:** p50 < 50ms for L1+L2 scoring. Deep LLM investigation runs asynchronously via Celery.

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
ollama serve && ollama pull llama3.1:8b &

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
├── observability/             # Monitoring (4 files)
│   ├── logging_config.py      # Structured logging (structlog)
│   ├── drift.py               # Population stability index + drift detection
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
├── dashboard/                 # Vite + React + TypeScript frontend
├── docker/                    # Dockerfiles + Compose (5 services)
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
| **L3: LLM** | Ollama (llama3.1:8b) | Natural language investigation reports (async via Celery) |
| **Explainability** | SHAP + GNNExplainer | Feature importance, evidence subgraphs |
| **Feedback** | Reflection Agent | FP clustering, drift detection, nightly weight auto-tuning |
| **A/B Testing** | Custom framework | Champion/challenger experiments with statistical significance |

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
| `OLLAMA_MODEL` | `llama3.1:8b` | Yes | LLM model name |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Yes | Task queue |
| `DATA_REGION` | `IN` | RBI | Data residency |
| `ENCRYPTION_KEY` | — | PCI-DSS | Data encryption |
| `ENABLE_HUMAN_REVIEW` | `false` | EU AI Act | Human oversight |

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
