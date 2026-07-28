# PayShield Technical Debt Register

## Debt Items

| ID | Description | Impact | Effort | Priority | Owner | Target |
|----|-------------|--------|--------|----------|-------|--------|
| TD-001 | Redis fallback uses in-memory LRU instead of distributed cache | Cache inconsistency during pod restarts | 2 days | P2 | TBD | Q1 2027 |
| TD-002 | GNN model requires full retrain — no incremental learning | 4-hour retrain window monthly | 2 weeks | P1 | TBD | Q4 2026 |
| TD-003 | Dashboard uses localStorage for auth tokens instead of httpOnly cookies | XSS vulnerability | 3 days | P2 | TBD | Q1 2027 |
| TD-004 | Ollama runs on CPU — evaluate GPU inference | LLM latency 2-5s vs potential sub-500ms | 1 week | P3 | TBD | Q2 2027 |
| TD-005 | No read replicas for PostgreSQL analytics queries | Reporting queries compete with production | 3 days | P2 | TBD | Q1 2027 |
| TD-006 | WebSocket connections not horizontally scalable (sticky sessions) | Connection limit per pod | 1 week | P3 | TBD | Q2 2027 |
| TD-007 | Celery task results not cleaned up in Redis | Redis memory grows unbounded | 1 day | P2 | TBD | Q3 2026 |
| TD-008 | No distributed tracing (OpenTelemetry not fully deployed) | Debugging cross-service issues is manual | 1 week | P2 | TBD | Q1 2027 |
| TD-009 | Test coverage below 80% for agents and compliance modules | Regression risk | 2 weeks | P2 | TBD | Q4 2026 |
| TD-010 | API rate limiter not distributed (in-memory per pod) | Ineffective with >1 replica | 2 days | P2 | TBD | Q4 2026 |

## Priority Definitions

| Priority | Mean Time to Fix | Examples |
|----------|-----------------|----------|
| P1 | < 1 month | Security vulnerabilities, data loss risk |
| P2 | < 3 months | Performance degradation, operational pain |
| P3 | < 6 months | Nice-to-have improvements, tech modernization |

## Remediation Plan

### Q3 2026
- TD-007: Celery result cleanup (1 day)
- TD-010: Distributed rate limiter (2 days)

### Q4 2026
- TD-002: Incremental GNN learning (2 weeks)
- TD-009: Agent/compliance test coverage (2 weeks)

### Q1 2027
- TD-001: Distributed cache (2 days)
- TD-003: httpOnly cookies (3 days)
- TD-005: PostgreSQL read replicas (3 days)
- TD-008: OpenTelemetry (1 week)

### Q2 2027
- TD-004: GPU inference for Ollama (1 week)
- TD-006: Horizontal WebSocket scaling (1 week)
