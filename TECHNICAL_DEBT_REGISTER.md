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

## Resolved Debt — Track 2 (live-stack verification, 2026-08-24)

Five issues surfaced only against the **real Docker stack** — the unit suite
used in-memory Redis fakes, so none were caught by tests. They were found by
running the containers (`docker compose up`), seeding demo data, and driving
the live endpoints; all fixed and covered by regression checks where possible.

| # | Bug / Finding | Root cause | Resolution | Commit |
|---|------------|-----------|-----------|--------|
| TD-101 | `/v1/return/update` returned **500** against real Redis (`redis.exceptions.DataError: Invalid input of type 'dict'`) | `AsyncRedisClient.hmset` passed the mapping **positionally** to redis-py `hset`, which reads it as the `key` arg | Pass the mapping by keyword (`hset(name, mapping=…)`) — the test double's `hset` was also updated to accept the `mapping=` kwarg. The return-risk write path (`update_user_profile`) was completely broken in production; hidden because FakeRedis's `hmset` was correct | `203c25b` |
| TD-102 | Seeding/worker scripts silently connected to `localhost` instead of the compose `redis` host inside containers | `create_redis` merged explicit `None` kwargs from `infrastructure.redis_bridge` over the configured `settings.redis.*` defaults, so `host=None` won | Non-`None` kwargs now override; `None` falls back to configured defaults — scripts hit the right host everywhere | `203c25b` |
| TD-103 | `SyncRedisClient` lacked `hmset`, so bulk hash writes were impossible via the sync client | Incomplete sync/async parity (the async client already had it) | Added `hmset(name, mapping, ttl=None)` to the sync client (same semantics as async) | `203c25b` |
| TD-104 | `scripts/seed_demo_data.py` crashed (`ModuleNotFoundError: No module named 'infrastructure'`) when run standalone | The script had no repo-root `sys.path` bootstrap (unlike the other Track 2 scripts) | Added the standard `sys.path.insert(0, parent)` bootstrap | `6509ebf` |
| TD-105 | The "suspicious burst" demo scenario couldn't fire its documented geo rules (`G-RULE-01/02`) | The seeder never wrote the prior-location key (`velocity:loc:U_FRAUD_001`) or the shared-device velocity history (`velocity:dev:DEV_SHARED_001`) | Seed the prior location (Mumbai, 20 min prior) and device burst; verified live: `BLOCK · 1.0 · [V-RULE-03, G-RULE-01, G-RULE-02]` | `6509ebf` |

**Follow-up lesson (TDD gap):** these bugs all lived in the *real* Redis
client layer while the test double mirrored a different, more permissive
interface. The suite is being hardened with parity-focussed tests for the
client doubles (`tests/unit/test_redis_clients.py`) so a fake can no longer
be more correct than the real client it stands in for.

## Priority Definitions

| Priority | Mean Time to Fix | Examples |
|----------|-----------------|----------|
| P1 | < 1 month | Security vulnerabilities, data loss risk |
| P2 | < 3 months | Performance degradation, operational pain |
| P3 | < 6 months | Nice-to-have improvements, polish |
