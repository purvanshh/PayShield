# PayShield — Real-Time UPI Fraud Detection Engine

**Multi-layer fraud scoring with graph-powered investigation and multi-agent orchestration.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Architecture

```
POST /v1/score
     │
     ▼
┌─────────────────────────────────────────────┐
│  Layer 1: Statistical Filter                 │
│  Velocity (6 rules) · Geo (4 rules) ·        │
│  Benford (2 rules) · Decision Gate           │
├─────────────────────────────────────────────┤
│  Layer 2: GNN Inference (PyTorch Geometric)  │
│  Heterogeneous graph: Users, Merchants,      │
│  Devices, Transactions                       │
├─────────────────────────────────────────────┤
│  Ensemble Fusion Engine                      │
│  Weighted fusion · Isotonic calibration ·    │
│  Disagreement logging                        │
├─────────────────────────────────────────────┤
│  Layer 3: LLM Investigation (Ollama/Celery)  │
│  Evidence collection · Narrative generation  │
│  SHAP explanations · Graph contexts          │
├─────────────────────────────────────────────┤
│  Reflection Agent (Feedback Loop)            │
│  FP clustering · Drift detection ·           │
│  Auto weight adjustment · Nightly analysis   │
└─────────────────────────────────────────────┘
     │
     ▼
  ALLOW / BLOCK / REVIEW
     │
     ▼
  WebSocket Alert + Investigation
```

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.11+ (for local development)

### Run with Docker Compose

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up
```

### Run Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and configure environment
cp .env.example .env

# 3. Start required services
redis-server &
ollama serve &
ollama pull llama3.1:8b

# 4. Initialize database
python scripts/init_db.py
python scripts/seed_redis.py

# 5. Start API
uvicorn api.main:app --reload --port 8000

# 6. Start Celery worker (in separate terminal)
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
  -d '{"txn_id":"TEST001","user_id":"U001","merchant_id":"M001","amount":500.0,"timestamp":"2026-07-29T12:00:00","device_fingerprint":"DEV001","location":{"lat":19.0760,"lon":72.8777},"mcc_code":"food","txn_type":"P2M"}'
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health (Redis, Neo4j, Ollama, Celery) |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/v1/score` | Score a single transaction |
| `POST` | `/v1/batch` | Score up to 100 transactions |
| `GET` | `/v1/investigation/{txn_id}` | Get LLM investigation report |
| `GET` | `/v1/investigations` | List all investigations (paginated) |
| `POST` | `/v1/feedback` | Submit analyst feedback |
| `GET` | `/v1/feedback/stats` | Feedback statistics |
| `WS` | `/v1/stream` | WebSocket for real-time alerts |
| `GET` | `/v1/stream/sse` | Server-Sent Events stream |
| `POST` | `/v1/graph/investigate` | Investigate entity in graph |
| `GET` | `/v1/graph/network/{entity_id}` | Get entity network (ego graph) |
| `POST` | `/v1/graph/entity` | Create graph entity |
| `POST` | `/v1/graph/link` | Link two entities in graph |
| `GET` | `/v1/graph/risk-paths` | Find risk paths between entities |
| `GET` | `/v1/graph/stats` | Graph database statistics |
| `GET` | `/admin/compliance/status` | Compliance framework status |
| `GET` | `/admin/compliance/check/{user_id}` | Sanctions + KYC check |
| `POST` | `/admin/compliance/sanctions/check` | OFAC/UN sanctions screening |
| `GET` | `/admin/compliance/kyc/{user_id}` | KYC verification status |
| `POST` | `/admin/compliance/aml/check` | AML velocity/structuring check |
| `POST` | `/admin/rules/reload` | Reload statistical rules from YAML |
| `POST` | `/admin/config/threshold` | Update scoring threshold |
| `GET` | `/admin/config` | View all configurations |
| `GET` | `/admin/agents/health` | Multi-agent health status |
| `POST` | `/admin/experiments` | Register A/B experiment |
| `GET` | `/admin/experiments` | List A/B experiments |

Full API docs available at `http://localhost:8000/docs` (Swagger) and `http://localhost:8000/redoc`.

## Project Structure

```
PayShield/
├── api/                    # FastAPI application
│   ├── routes/             # Route handlers (score, investigation, feedback, graph, etc.)
│   ├── main.py             # App factory with middleware wiring
│   ├── schemas.py          # Pydantic request/response models
│   ├── dependencies.py     # Dependency injection (Redis, ensemble, auth)
│   ├── exceptions.py       # Typed exception hierarchy
│   ├── middleware.py        # Correlation ID, timing, security headers
│   ├── websocket.py        # WebSocket manager with room-based routing
│   └── lifespan.py         # Startup/shutdown resource lifecycle
├── engine/                 # Scoring & decision engine
│   ├── statistical_filter.py  # Layer 1: Velocity, Geo, Benford filters
│   ├── ensemble.py         # Layer 2+ fusion: EnsembleFusionEngine, Calibrator
│   ├── graph_model.py      # PyTorch Geometric GNN model
│   ├── graph_feature_engine.py  # Feature extraction from graph
│   ├── graph_builder.py    # Heterogeneous graph construction
│   ├── graph_loader.py     # Graph data loading
│   └── explainer.py        # GNNExplainer + SHAP bridge
├── agents/                 # Multi-agent framework (Reflection, HumanReview, etc.)
├── llm/                    # Ollama LLM integration
├── compliance/             # PCI-DSS, RBI, EU AI Act, Sanctions, AML, KYC
├── data/                   # Data generation & features
│   ├── synthetic/          # Synthetic UPI transaction generator
│   ├── features/           # Benford's Law, geospatial, velocity
│   └── validation/         # Data quality validator
├── store/                  # Data stores (Redis, PostgreSQL, Neo4j, graph)
├── tasks/                  # Celery tasks (investigation, reflection, compliance)
├── infrastructure/         # Redis bridge (sync/async client factory)
├── observability/          # Logging, metrics, drift detection
├── ml/                     # Model training, registry, A/B testing
├── configs/                # YAML configuration (rules, features, RBAC, thresholds)
├── alembic/                # Database migrations
├── tests/                  # Test suite (unit, integration, e2e, load)
├── scripts/                # Bootstrap scripts (init_db, seed_redis, create_admin)
├── docker/                 # Docker Compose + Dockerfiles
├── k8s/                    # Kubernetes manifests (base + overlays)
└── sre/                    # SLOs, runbooks, error budgets, chaos experiments
```

## Training Models

Model artifacts (`.pkl`, `.onnx`, `.pt`) are generated by the training pipeline:

```bash
# Generate synthetic training data
python -m data.synthetic.generator --n-txns 100000

# Train the GNN model
python -m ml.train --epochs 50 --batch-size 256

# Register and promote to production
# (via admin API)
curl -X POST http://localhost:8000/admin/models/promote \
  -H "X-API-Key: payshield-dev-key-2026" \
  -d '{"version": "v1.1.0", "stage": "production"}'
```

See `models/README.md` for artifact conventions.

## Dashboard (Frontend)

The dashboard is under active development in `dashboard/` (React + TypeScript + Vite). It is currently a **Phase 48-49 WIP** with mock data mode for frontend development:

```bash
cd dashboard
npm install
npm run dev          # Starts on http://localhost:5173
```

The dashboard connects to:
- `VITE_API_URL` (default: `http://localhost:8000`) for REST API
- `VITE_WS_URL` (default: `ws://localhost:8000`) for real-time alerts

## Environment Variables

See `.env.example` for all configurable variables. Required for operation:

| Variable | Default | Required |
|----------|---------|----------|
| `PAYSHIELD_DEV_API_KEY` | `payshield-dev-key-2026` | Dev only |
| `REDIS_HOST` | `localhost` | Yes |
| `REDIS_PORT` | `6379` | Yes |
| `DATABASE_URL` | `postgresql+asyncpg://...` | For persistence |
| `NEO4J_URI` | `bolt://localhost:7687` | For graph |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | For async tasks |

## CI Pipeline

```yaml
lint → type-check → test → build
```

- **Lint**: `ruff check .`
- **Type check**: `mypy api/ engine/ agents/`
- **Tests**: `pytest --cov=payshield --cov-report=term-missing`
- **Build**: Docker image build + push

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Quick checklist:

1. Run `ruff check .` and fix all issues
2. Run `pytest` and ensure tests pass
3. Add tests for new functionality
4. Update `.env.example` if new env vars are introduced
5. Never commit secrets or API keys

## License

MIT — see [LICENSE](LICENSE)
