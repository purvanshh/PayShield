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
Transaction → Feature Extraction → Ensemble Inference
                                        ↓
                            ┌───────────────────┐
                            │ Confidence ≥ 0.9? │
                            └───────┬───┬───────┘
                               Yes  │   │  No
                                ↓    │   ↓
                           Approve   │   LLM Investigator
                                     │        ↓
                                     │   Agent Orchestrator
                                     │        ↓
                                     │   Final Decision
                                     │        ↓
                                     │   Human Review (if needed)
```

### Request Flow

1. **Client** sends transaction data via REST or WebSocket
2. **API Gateway** authenticates, rate-limits, routes
3. **Feature Pipeline** extracts 200+ features
4. **Ensemble Fusion** runs 5 models + meta-learner
5. **Decision Logic** uses confidence thresholds
6. **LLM Investigator** (optional) deep-dives
7. **Agent Orchestrator** consults 8 specialized agents
8. **Storage** persists result to PostgreSQL
9. **Response** returned to client (~50-100ms)

## Components

### API Layer
- FastAPI application with OpenAPI docs
- JWT-based authentication
- Rate limiting (token bucket)
- Request/response validation via Pydantic
- Prometheus metrics endpoint

### ML Engine
- 5 ensemble models + Gradient Boosting meta-learner
- Weighted voting fusion strategy
- Confidence-based decision routing
- Online learning from feedback
- Model versioning and A/B testing

### LLM Investigator
- Structured prompts for fraud analysis
- Transaction context enrichment
- Risk scoring with reasoning
- Support for multiple LLM providers
- Configurable investigation depth

### Agent System
8 specialized agents:
1. **Transaction Agent** - Core transaction analysis
2. **Risk Agent** - Risk scoring and aggregation
3. **Pattern Agent** - Pattern matching and anomaly detection
4. **Behavior Agent** - Behavioral analysis
5. **History Agent** - Historical context lookup
6. **Network Agent** - Network analysis (merchant, IP, device)
7. **Compliance Agent** - Regulatory checks
8. **Decision Agent** - Final decision synthesis

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
