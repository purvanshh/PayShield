# Development Guide

## Project Structure

```
payshield/
├── return_risk/         # ★ Evaluated hero: feature engine, rules, XGBoost scorer
├── api/                 # FastAPI application
│   ├── main.py          # App factory & router wiring
│   ├── routes/          # return_risk, health, auth, admin, experiments, meta (+ chargeback/score extensions)
│   ├── middleware.py    # Auth, rate-limit, timing, CORS, security headers
│   ├── dependencies.py  # verify_api_key, get_redis, rate limits
│   ├── auth.py          # JWT, TOTP MFA, API key verification
│   ├── security.py      # Rate limiter (Redis incr+TTL)
│   └── lifespan.py      # Startup/shutdown resource lifecycle
├── engine/              # (extension) fraud: L1 statistical filter, L2 GNN, ensemble
├── chargeback/          # (extension) dispute rebuttal builder + Razorpay client
├── store/               # Redis client, audit log, connection pool (+ fraud graph store)
├── integrations/        # Razorpay adapter + webhooks (order.paid → score)
├── ml/                  # return-risk champion/challenger A/B + model lifecycle
├── observability/       # PSI drift monitoring (return-risk surface)
├── data/synthetic/      # return-risk generator (non-circular DGP)
├── scripts/             # train/ablation/tune/benchmark/verify — the evidence
├── configs/             # YAML configuration (return_risk_rules, feature_registry, RBAC)
├── tests/               # Test suite (498 tests)
│   ├── unit/            # incl. return_risk/ scorer, feature engine, rules
│   ├── integration/     # API, return-risk, chargeback, security
│   ├── e2e/             # End-to-end (needs live services)
│   └── fake_redis.py    # In-memory async Redis (single source of truth)
├── docs/                # Documentation
└── models/              # Return-risk model artifacts + cost model
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
- Coverage gates: TOTAL ≥ 70%, `return_risk/*` ≥ 80%

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
# Build and start the stack (api + redis)
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d

# API only
docker compose -f docker/docker-compose.yml up api -d
```

## Environment-Specific Configuration

| Environment | Config File | Notes |
|-------------|------------|-------|
| Development | `.env` | Local overrides |
| Testing | `.env.test` | CI/CD pipeline |
| Staging | `.env.staging` | Pre-production |
| Production | `.env.prod` | Env-secret config, rotate dev defaults |

## Common Tasks

### Adding a New API Endpoint

1. Create route in `api/routes/`
2. Add Pydantic schemas in the route file
3. Register in `api/main.py:_include_routers()`
4. Add authentication if needed via `Depends(verify_api_key)`
5. Add RBAC if needed via `Depends(require_permission(...))`
6. Add tests in `tests/integration/`
