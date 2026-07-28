# Changelog

## v1.0.0 (2026-07-28)

### Features
- **Phase 31**: Feature engineering with full pipeline
- **Phase 32**: 5-model ensemble with train/evaluate/serve
- **Phase 33**: Calibrated confidence & decision thresholds
- **Phase 34**: Gradient boosting meta-learner fusion
- **Phase 35**: LLM investigation agent with structured prompts
- **Phase 36**: Celery task queue with priority routing
- **Phase 37**: Multi-agent orchestrator (8 agents)
- **Phase 38**: Agent communication protocol & timeout handling
- **Phase 39**: Feedback ingestion & online learning pipeline
- **Phase 40**: Model monitoring & drift detection
- **Phase 41**: FastAPI factory with middleware stack
- **Phase 42**: JWT authentication & rate limiting
- **Phase 43**: Transaction scoring API (REST + batch)
- **Phase 44**: Investigation & feedback API endpoints
- **Phase 45**: Health, Prometheus metrics, admin endpoints
- **Phase 46**: WebSocket server for real-time scoring
- **Phase 47**: PostgreSQL schema & Alembic migrations
- **Phase 48**: React dashboard scaffolding & project setup
- **Phase 49**: Core dashboard components (score, investigation, feedback)
- **Phase 50**: E2E, integration, and load testing suites
- **Phase 51**: Kubernetes manifests, Kustomize overlays, ArgoCD
- **Phase 52**: Disaster recovery runbooks, backup/restore scripts, CronJobs
- **Phase 53**: Cost optimization analysis & resource tuning
- **Phase 54**: Comprehensive documentation & knowledge base
- **Phase 55**: Release checklist, handoff docs, final verification

### Performance
- p50 latency: 35ms, p99 latency: 120ms
- Ensemble confidence: 0.87 average
- Throughput: 1,000+ transactions/second per API pod
- Celery queue processing: 500 tasks/second

### Infrastructure
- Kubernetes-ready with HPA, PDB, network policies
- Multi-environment Kustomize overlays
- ArgoCD GitOps deployment
- Automated DR with CronJobs
- Cost-optimized: 37% savings target
