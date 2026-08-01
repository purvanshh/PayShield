# Development Guide

## Project Structure

```
payshield/
├── api/                # FastAPI application
│   ├── main.py         # App factory & startup
│   ├── routes/         # API endpoints (score, investigation, feedback, etc.)
│   ├── middleware.py   # Middleware (auth, rate-limit, timing, CORS, security headers)
│   ├── dependencies.py # Dependency injection (verify_api_key, get_redis, rate limits)
│   ├── auth.py         # JWT, TOTP MFA, API key verification
│   ├── security.py     # Rate limiter (Redis incr+TTL, IP sliding window)
│   └── lifespan.py     # Startup/shutdown resource lifecycle
├── engine/             # Scoring & decision engine
│   ├── statistical_filter.py  # L1: 12 rules (velocity, geo, Benford)
│   ├── ensemble.py            # Weighted fusion + isotonic calibrator
│   ├── graph_model.py         # HeteroConv+SAGEConv GNN
│   └── graph_feature_engine.py # Ego-graph extraction
├── store/              # Data stores
│   ├── redis_client.py       # AsyncRedisClient (circuit breaker)
│   ├── audit_log.py          # Hash-chained JSONL + async queue writer
│   ├── graph_db.py           # NetworkXGraphDB (fallback)
│   └── connection_pool.py    # Redis pool + circuit breaker
├── compliance/         # Programmatic compliance checkers
│   ├── pci_dss.py, rbi_localization.py, eu_ai_act.py
├── agents/             # 14-agent framework (12 concrete + router + state)
├── ml/                 # ML lifecycle (train, registry, A/B testing, inference)
├── llm/                # Ollama LLM integration (client, prompts, parser, investigator)
├── tasks/              # Celery async tasks
├── configs/            # YAML configuration (rules, RBAC, thresholds, features)
├── tests/              # Test suite (392 tests, 74% coverage)
│   ├── unit/           # 13+ unit test files
│   ├── integration/    # API, score-path, security integration tests
│   ├── e2e/            # End-to-end tests (needs live services)
│   └── fake_redis.py   # In-memory async Redis (single source of truth)
├── docs/               # Documentation
└── models/             # Model artifacts + fairness audit
```

## Coding Standards

### Python

- Follow PEP 8 (use `ruff` for linting)
- Type hints required for all functions
- Docstrings for public APIs (Google style)
- Max line length: 100 characters

```bash
make lint    # Run linters
make format  # Auto-format code
make typecheck  # Run mypy
```

### Naming Conventions

- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_prefix`
- Modules: short, lowercase, no underscores

### Testing

```bash
# Run all tests
.venv-test/bin/python -m pytest tests/ -q

# Run with coverage
.venv-test/bin/python -m pytest tests/ -q --cov --cov-report=term

# Unit tests only
.venv-test/bin/python -m pytest tests/unit/ -q

# Integration tests only
.venv-test/bin/python -m pytest tests/integration/ -q

# Single test file
.venv-test/bin/python -m pytest tests/unit/test_security_hardening.py -q
```

Testing conventions:
- `tests/fake_redis.py` — in-memory async Redis (single source of truth, never per-test patch)
- `tests/conftest.py` — autouse fixture for hermetic rate limiter
- Coverage gates: TOTAL ≥ 70%, score.py ≥ 80%, ensemble.py ≥ 80%, graph_feature_engine.py ≥ 80%

## Git Workflow

```
main        ─── Production-ready code
  ├── develop    ─── Integration branch
  │   ├── feature/*  ─── New features
  │   ├── fix/*      ─── Bug fixes
  │   └── refactor/* ─── Refactoring
```

### Commit Messages

```
<type>(<scope>): <description>

feat:     New feature
fix:      Bug fix
refactor: Code restructuring
test:     Test additions/changes
docs:     Documentation
chore:    Maintenance
```

## Docker Development

```bash
# Build images
make docker-build

# Start services
make dev

# Run specific service
docker compose up api -d
docker compose up celery-worker -d
```

## Environment-Specific Configuration

| Environment | Config File | Notes |
|-------------|------------|-------|
| Development | `.env` | Local overrides |
| Testing | `.env.test` | CI/CD pipeline |
| Staging | `.env.staging` | Pre-production |
| Production | `.env.prod` | K8s secrets |

## Common Tasks

### Adding a New API Endpoint

1. Create route in `api/routes/`
2. Add Pydantic schemas in the route file
3. Register in `api/main.py:_include_routers()`
4. Add authentication if needed via `Depends(verify_api_key)`
5. Add RBAC if needed via `Depends(require_permission(...))`
6. Add tests in `tests/integration/`
