# PayShield Technical Debt Register

## Active Debt Items

| ID | Description | Impact | Effort | Priority | Phase |
|----|-------------|--------|--------|----------|-------|
| TD-002 | GNN model requires full retrain — no incremental learning | Requires offline retrain cycle per new data batch | 2 weeks | P2 | — |
| TD-003 | Dashboard uses localStorage for auth tokens instead of httpOnly cookies | XSS risk if an injected script reads tokens | 3 days | P2 | — |
| TD-004 | Ollama runs on CPU — evaluate GPU inference | ~35 s per investigation; GPU would cut to sub-second | 1 week | P3 | — |
| TD-005 | No read replicas for PostgreSQL analytics queries | Reporting competes with production | 3 days | P3 | — |
| TD-006 | WebSocket connections not horizontally scalable (sticky sessions) | Connection limit per pod | 1 week | P3 | — |
| TD-007 | Celery task results not cleaned up in Redis | Redis memory grows unbounded | 1 day | P2 | — |
| TD-008 | No distributed tracing (OpenTelemetry not deployed) | Debugging cross-service issues is manual | 1 week | P3 | — |
| TD-009 | Dashboard UI is minimal (3 pages, inline styles) | Functional but not production-polished | 2 weeks | P3 | — |
| TD-013 | GNN trained on synthetic data only | Real UPI traffic has different seasonality and mule-ring density | N/A | P2 | — |

## Resolved Debt (P5–P10)

| ID | Description | Resolution | Phase |
|----|-------------|------------|-------|
| TD-010 | API rate limiter not distributed (in-memory per pod) | Redis incr+TTL fixed-window per-key (1000/hr) and per-user rate limits. Middleware IP guard remains as coarse fallback. | P9 |
| TD-011 | MFA not implemented for admin accounts (PCI-DSS 8.3) | RFC 6238 TOTP (SHA-1, 30s step, 6 digits, pure stdlib). `/auth/totp/setup` + `/auth/totp/verify` admin-only endpoints. Module-level auth_manager singleton preserves state across requests. | P9 |
| TD-012 | L2 GNN benchmarked but not fused into live `/v1/score` | Phase 3: `_run_l2_inference` with 5 status codes (SUCCESS / SKIPPED_NO_GRAPH / TIMEOUT / MODEL_UNAVAILABLE / ERROR), 40 ms timeout guard, L1-only fallback on any failure. Ensemble isotonically calibrated (ECE 0.055→0.010). | P3–P4 |
| TD-001 | Redis fallback uses in-memory LRU instead of distributed cache | Circuit breaker + fallback cache pattern already covers Redis failures. Separate distributed cache adds complexity without measurable gain at current scale. | WONTFIX |
| — | PSI estimator was 11× inflated (43.4 false spike) | Shared quantile bin edges + bin-count scaling + Laplace smoothing → actual 3.86 | P5 |
| — | Drift samples never recorded (missing await) | Awaited; zset member/score convention standardized | P5 |
| — | `list_investigations` N+1 GETs | Pipeline/MGET batching (1 round trip) | P9 |
| — | `get_entity_network` no pagination | limit/offset with `has_more` flag | P9 |
| — | Audit log synchronous file I/O on hot path | AsyncAuditLogWriter — asyncio.Queue + background worker, batch flush (100 entries or 1s), <1ms hot-path append | P9 |
| — | JWT refresh revocation bug (storing raw token instead of jti) | Fixed: decode payload, extract jti, add jti to revoked set | P9 |
| — | CORS allow_origins=["*"] | Env-driven `FRONTEND_URL`, no wildcard | P9 |
| — | `verify_chain()` hash recomputation included entry_id | Fixed: `{k: v for k, v in entry if k not in ("hash", "entry_id")}` | P9 |
| — | Test coverage below gates | 392 tests, 74% total (gates: score 91%, ensemble 90%, graph 99%) | P5 |
| — | EU AI Act checker incomplete | 13 controls, 100/100 score | P10 |

## Priority Definitions

| Priority | Mean Time to Fix | Examples |
|----------|-----------------|----------|
| P1 | < 1 month | Security vulnerabilities, data loss risk |
| P2 | < 3 months | Performance degradation, operational pain |
| P3 | < 6 months | Nice-to-have improvements, polish |
