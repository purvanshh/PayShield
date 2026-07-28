# Development Guide

## Project Structure

```
payshield/
├── api/                # FastAPI application
│   ├── main.py         # App factory & startup
│   ├── routes/         # API endpoints
│   ├── middleware/      # Middleware (auth, rate-limit, etc.)
│   └── websocket/      # WebSocket handlers
├── ml/                 # Machine learning
│   ├── models/         # 5 ensemble models
│   ├── features/       # Feature engineering pipeline
│   ├── ensemble/       # Fusion strategies
│   └── training/       # Training pipeline
├── llm/                # LLM integration
│   └── investigator/   # LLM investigation agent
├── agents/             # Multi-agent system
│   └── orchestrator/   # 8 specialized agents
├── engine/             # Core engine
│   ├── rules/          # Rule-based detection
│   └── pipeline/       # Processing pipeline
├── tasks/              # Celery tasks
├── dashboard/          # React dashboard
├── k8s/                # Kubernetes manifests
├── dr/                 # Disaster recovery
├── cost/               # Cost optimization
├── scripts/            # Utility scripts
├── tests/              # Test suite
└── docs/               # Documentation
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
make test              # Run all tests
make test-unit         # Unit tests only
make test-integration  # Integration tests only
make test-e2e          # End-to-end tests
```

Testing conventions:
- Unit tests: `tests/test_*.py`
- Fixtures in `tests/conftest.py`
- Factories in `tests/factories.py`
- Mock external services

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

### Adding a New Model

1. Create model class in `ml/models/`
2. Register in `ml/ensemble/base.py`
3. Add training routine in `tasks/training.py`
4. Add tests in `tests/test_ml/`

### Adding a New API Endpoint

1. Create route in `api/routes/`
2. Add schemas in `api/schemas/`
3. Register in `api/main.py`
4. Add authentication if needed
5. Add tests in `tests/test_api/`

### Adding a Celery Task

1. Define task in `tasks/`
2. Register in `tasks/__init__.py`
3. Configure routing in `tasks/celery_app.py`
4. Handle results in appropriate consumer
