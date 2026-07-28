# PayShield Documentation

Enterprise fraud detection system powered by ensemble ML, LLM investigation, and multi-agent orchestration.

## Quick Links

- [Getting Started Guide](guides/getting-started.md)
- [Architecture Overview](architecture/overview.md)
- [API Reference](api/endpoints.md)
- [Operations Manual](operations/deployment.md)
- [Training Guide](training/onboarding.md)

## System Overview

PayShield processes real-time transactions through a multi-layered pipeline:

1. **Feature Engineering** - Extracts 200+ features from raw transactions
2. **Ensemble Inference** - 5 specialized models + meta-learner
3. **LLM Investigation** - Optional deep-dive on borderline cases
4. **Multi-Agent Orchestration** - 8 specialized agents for complex decisions
5. **Feedback Loop** - Continuous learning from human feedback

## Key Features

- Real-time fraud detection (sub-100ms latency)
- Ensemble of 5 ML models (XGBoost, LightGBM, CatBoost, RF, MLP)
- LLM-powered investigation and reasoning
- Multi-agent system with 8 specialized agents
- Celery-based async task processing
- WebSocket for real-time streaming
- PostgreSQL for durable storage
- Prometheus/Grafana observability
- Comprehensive DR/backup strategy
- Kubernetes-native deployment

## Tech Stack

| Component | Technology |
|-----------|------------|
| API | FastAPI (Python 3.12) |
| ML | scikit-learn, XGBoost, LightGBM, CatBoost |
| LLM | OpenAI-compatible API |
| Queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Streaming | WebSocket |
| Infra | Docker, Kubernetes, ArgoCD |
| Monitoring | Prometheus, Grafana, Sentry |
| CI/CD | GitHub Actions |
