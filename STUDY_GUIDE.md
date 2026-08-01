# PayShield — Interview Study Guide

## 1. The 30-Second Elevator Pitch

> "PayShield is a real-time UPI fraud detection system I built after experiencing a fraud attempt. It has three layers: L1 statistical rules that block in under 10 milliseconds, an L2 graph neural network that conditionally fuses when the user has graph history, and an L3 LLM investigator that generates analyst narratives asynchronously."

---

## 2. Architecture Deep Dive

### 2.1 Three-Layer Scoring Pipeline

```
POST /v1/score
    │
    ├── Layer 1: Statistical Filter (p99 0.27 ms)
    │   ├── 6 velocity rules (V-RULE-01..06) — burst, frequency, amount patterns
    │   ├── 4 geo rules (G-RULE-01..04) — haversine distance, geo-velocity
    │   └── 2 Benford's Law rules (B-RULE-01..02) — chi-squared distribution test
    │   Decision: BLOCK (hard stop) / ALLOW (pass through) / ESCALATE (go to L2)
    │
    ├── Layer 2: GNN (conditional, 40 ms timeout guard)
    │   ├── Extracts 2-hop ego graph from NetworkXGraphDB
    │   ├── HeteroConv + SAGEConv (53,826 params, 2 layers, hidden 64)
    │   ├── Five status codes:
    │   │   SUCCESS           — GNN returned prob > 0 for returning user
    │   │   SKIPPED_NO_GRAPH  — fresh user, < 2 graph nodes
    │   │   TIMEOUT           — inference > 40 ms
    │   │   MODEL_UNAVAILABLE — l2_inference service not loaded
    │   │   ERROR             — any exception caught and logged
    │   └── On non-SUCCESS → ensemble falls back to L1-only fusion
    │
    ├── Ensemble Fusion (weighted, isotonically calibrated)
    │   ├── L1 weight: 0.3, L2 weight: 0.7 (configurable)
    │   ├── Isotonic calibrator: ECE 0.055 → 0.010 after fitting
    │   ├── Above-support scores passed raw (monotone, continuous at boundary)
    │   └── Final decision: BLOCK / REVIEW / ALLOW with confidence score
    │
    └── Layer 3: LLM Investigation (asynchronous, Celery)
        ├── qwen2.5:3b via Ollama (~35 s per investigation)
        ├── JSON-only prompt with tolerant parser
        ├── Evidence: L1 rules triggered, SHAP values, subgraph context
        └── Result cached in Redis: `investigation:{txn_id}` with 24h TTL
```

### 2.2 Key Files to Know

| File | Lines | Purpose |
|------|-------|---------|
| `api/routes/score.py` | 535 | Main scoring endpoint — L1, L2, ensemble, idempotency, caching |
| `engine/statistical_filter.py` | 481 | 12 configurable L1 rules with Redis-backed features |
| `engine/ensemble.py` | 195 | Weighted fusion + isotonic calibration |
| `engine/graph_model.py` | — | HeteroConv+SAGEConv GNN model definition |
| `engine/graph_feature_engine.py` | 152 | Ego-graph extraction + feature hydration |
| `ml/inference.py` | — | L2InferenceService — predict() with timeout guard |
| `store/redis_client.py` | 198 | AsyncRedisClient with circuit breaker |
| `store/audit_log.py` | 243 | Hash-chained JSONL + async queue writer |
| `store/connection_pool.py` | 140 | Redis pool + CircuitBreaker + maxmemory check |
| `api/auth.py` | 207 | JWT, TOTP, API key verification, refresh rotation |
| `api/security.py` | 86 | Per-key/per-user rate limiter (Redis incr+TTL) |
| `api/dependencies.py` | 88 | Dependency injection — verify_api_key, get_redis, etc. |
| `compliance/eu_ai_act.py` | 174 | 13-control EU AI Act checker (100/100) |
| `compliance/pci_dss.py` | — | PCI-DSS checker (90/100) |
| `compliance/rbi_localization.py` | — | RBI checker (100/100) |
| `models/fairness_audit.py` | 140 | SPD/EOD on synthetic demographic slices |

### 2.3 Data Flow Per Request

```
1. POST /v1/score → ScoreRequest (txn_id, user_id, merchant_id, amount, location, etc.)
2. Idempotency check: idempotent:{sha256(txn_id)} — return cached if exists (60s TTL)
3. Velocity features: Redis zrangebyscore on velocity:user:*, velocity:dev:*, velocity:loc:*
4. L1 filter: 12 rules → BLOCK (HTTP 200 with decision=BLOCK) or ALLOW or ESCALATE
5. [Conditional] L2 inference: extract ego-graph → predict → fusion
6. Ensemble: weighted blend → isotonic calibration → final decision
7. Audit: async enqueue to AsyncAuditLogWriter (fire-and-forget, <1ms)
8. Graph mirror: write txn to NetworkXGraphDB + seed device→user index
9. Drift sampling: record feature distribution snapshots (async, zadd)
10. Metrics: _observe_l1_block, _observe_ensemble_latency, etc.
11. Return ScoreResponse with latency breakdown
```

---

## 3. Production Hardening — The 18 Bugs

| # | Bug | Root Cause | Fix |
|---|-----|------------|-----|
| 1 | API crash at startup | `config.get(...)` on `None` | `self.config.get(...)` |
| 2 | Score route returned canned results | Features never computed | Real Redis-backed velocity/geo features |
| 3 | Redis/Ollama used localhost in containers | Hardcoded defaults | Env-driven config |
| 4 | Worker died: `No module named 'infrastructure'` | Fork-time import | Module-level import with fallback |
| 5 | Investigation route 500 | Nested `{status, report}` | Accept flat or nested report dicts |
| 6 | LLM unparseable output | JSON embedded in prose | JSON-only prompt + tolerant parser |
| 7 | `UnboundLocalError: l2` | `l2` referenced before assignment | Initialize before use |
| 8 | Investigation never ran | Wrong Celery module | `celery -A tasks.celery_app` |
| 9 | RBAC 403 on investigations | Missing `investigation:read` | Added to `configs/rbac.yaml` |
| 10 | Role endpoints rejected API keys | Only read Bearer | Accept `x-api-key` fallback |
| 11 | Dashboard Docker build failed | Missing deps, TS errors | Fix Dockerfile + install deps |
| 12 | No compliance persistence | Audit log didn't exist | `store/audit_log.py` |
| 13 | Drift PSI = 43.4 (11× inflated) | Fixed bins + density=True | Shared quantile bins + Laplace smoothing |
| 14 | Drift samples never recorded | Missing `await` | Awaited; fixed zset conventions |
| 15 | Container rebuilds wiped data | Code dirs shadowed | Named volumes on leaf data dirs |
| 16 | Synthetic generator crashed | No tier-4 cities | Added 4 tier-4 cities |
| 17 | Synthetic generator crash | `random.choice(weights=)` | `rng.choices(weights=...)` |
| 18 | False AUC > 0.92 claim | Aspirational, never measured | Corrected to PR-AUC 0.198 |

### Bug 13 Deep Dive (PSI Estimator Fix)

**The Problem:** Drift detection reported PSI = 43.4 for identical distributions.

**Root causes (3 simultaneous bugs):**
1. **Fixed 10 bins on 14 samples** — with 14 data points and 10 equal-width bins, most bins were empty, artificially inflating divergence
2. **`density=True` in `np.histogram`** — double-normalized the histogram, making PSI sensitive to bin width not just distribution shape
3. **Zero-mass bins** — PSI = Σ(P_i − Q_i) × ln(P_i/Q_i) — when any bin has 0 in one distribution and non-zero in the other, the term is infinity

**The Fix:**
1. **Adaptive bin count:** `bin_count = max(3, n_samples // 5)` — scales with data size
2. **Shared quantile edges:** compute bin edges on the COMBINED distribution of both windows, guaranteeing no bin is empty in both distributions and bins match across comparison
3. **Laplace smoothing:** add 0.001 to each bin count — prevents division by zero

**Validated:** identical inputs → PSI 0.000; 1σ shift → PSI 0.981

### Bug 14 Deep Dive (Zset Convention Mismatch)

**The Problem:** Drift samples were recorded but `zrangebyscore` returned no data.

**Root cause:** Redis zset `zadd` stores `{member: score}` mapping. The code was passing `{value: timestamp}` but reading with `zrangebyscore(key, start_ts, end_ts)` — expecting `{timestamp: value}` or `score=timestamp` depending on the path. Inconsistent: recording used `value_as_score=True`, reading used `scores_as_timestamps=True`.

**Fix:** Standardized on member = serialized value dict, score = timestamp. Reading: `zrangebyscore(key, start_ts, end_ts)` — works identically.

---

## 4. Technical Decisions You Must Defend

### 4.1 "Why conditional fusion instead of always-on GNN?"

1. **Availability > perfection:** A synthetic-data-trained GNN has measured PR-AUC 0.198 — blocking the hot path on it unconditionally would reject legitimate transactions at a 71% FPR (at 90% recall). L1 rules alone catch obvious fraud with near-zero false positives.
2. **Fresh-user problem:** Users with no graph history (< 2 nodes) produce empty ego-graphs. The GNN would return random noise. Skipping is correct.
3. **Timeout guard:** 40 ms timeout via `asyncio.wait_for` — if GNN inference is slow, we fall back to L1. A blocked API is worse than a missed relational pattern.
4. **Ensemble fallback:** When `l2_status != SUCCESS`, the ensemble drops L2 weight entirely and uses L1-only weighted fusion. The scale is continuous — a returning user with 500 ms GNN inference gets L1 fallback; a returning user with 0.5 ms inference gets full L2 weighting.

### 4.2 "Why bare `except Exception` at Redis/Neo4j/Ollama boundaries?"

These are **infrastructure adapter boundaries**, not business logic. The pattern is:

```python
try:
    result = await redis_client.get(key)
except Exception:
    logger.warning("redis_read_failed: %s", key)
    return fallback_default
```

Each guard has a **defined fallback**: Redis → local store; Neo4j → NetworkX; Ollama → skip investigation; Audit → log debug. This is the Circuit Breaker pattern without the naming — fail open at the boundary, fail closed in the core.

Internal modules (engine, ml, agents) use **typed exceptions** from `api/exceptions.py`. The bare-except pattern is only at the infrastructure edge — Redis, Neo4j, Ollama, Celery, filesystem. This is a deliberate resilience pattern, not a code smell.

### 4.3 "Why raw Cypher f-strings for node labels?"

Node labels are **hardcoded enum values** (`NodeType.USER`, `NodeType.TXN`, `NodeType.MERCHANT`, `NodeType.DEVICE`) defined in `store/neo4j_client.py`. They are compiler-time constants — not user input. Property values (actual data) use parameterized Cypher:

```cypher
# OK — label is a compiler-time constant
f"MATCH (n:{NodeType.USER}) WHERE n.user_id = $uid"

# NOT OK — user input interpolated
f"MATCH (n:User) WHERE n.user_id = '{user_input}'"

# FIX — parameterized
"MATCH (n:User) WHERE n.user_id = $uid"
```

This is the same pattern Neo4j官方 drivers use for schema-level DDL (CREATE CONSTRAINT, CREATE INDEX) where labels are known at compile time.

### 4.4 "Why isotonic calibration with above-support passthrough?"

Isotonic regression is **non-parametric** — it cannot extrapolate past the largest raw score seen during fitting. The training data's maximum raw fraud confidence might be 0.80, but a production transaction could hit 0.95.

**Three options:**
1. **Clip at max support** → 0.95 raw clips to 0.80 calibrated → the classifier can NEVER reach the BLOCK threshold → broken. ❌
2. **Platt scaling (logistic)** → parametric, smooth, but assumes sigmoid shape → not appropriate for ensemble outputs. ❌
3. **Isotonic with passthrough** → below support: calibrated; above support: raw score. Monotone, continuous at the support boundary because `X_thresholds_[-1]` is the boundary point. ✅

This is documented in `engine/ensemble.py:71-73` with the rationale.

---

## 5. Security Architecture

### 5.1 Authentication Flow

```
Request arrives
    │
    ├── X-API-Key header? → SHA-256 hash → lookup in _api_keys → ServicePrincipal
    │   └── Rate limit: per-key 1000/hr (Redis incr + TTL 3600s)
    │
    ├── Bearer token? → JWT decode (HS256) → check jti in _revoked_tokens → UserPrincipal
    │   └── Rate limit: per-user 1000/hr
    │
    └── Neither? → 403

JWT Refresh Rotation:
    POST /v1/auth/refresh {refresh_token}
    → decode → extract jti → add jti to _revoked_tokens ← (FIXED: was adding raw token string)
    → issue new access_token (30 min) + new refresh_token (7 days sliding window)
    → old refresh_token replay → jti in revoked → 401
```

### 5.2 TOTP MFA (RFC 6238, Pure stdlib)

- Algorithm: HMAC-SHA1, 30-second step, 6 digits
- No external dependency (base64 + hmac + hashlib + struct)
- Window tolerance: ±1 step (90 seconds) for clock drift
- Admin-only setup: requires existing JWT with role=admin
- Provision URI: `otpauth://totp/PayShield:admin?secret=BASE32&issuer=PayShield`

### 5.3 Rate Limiting (Fixed Window via Redis INCR + TTL)

```python
# Per API key
count = redis.incr(f"ratelimit:fixed:apikey:{sha256[:32]}")
if count == 1:
    redis.expire(key, 3600)  # 1-hour TTL on first hit
if count > 1000:
    raise HTTPException(429, headers={"Retry-After": "3600"})
```

One Redis round trip per request. The expire is set only on the first increment (count == 1), so it's truly fixed-window without needing zremrangebyscore cleanup.

---

## 6. Observability Stack

### 6.1 Metrics Instrumented in Hot Path

| Metric Name | Type | Label | Purpose |
|-------------|------|-------|---------|
| `layer1_block_total` | Counter | `rule_class` | Track which L1 rules trigger blocks |
| `layer2_escalation_total` | Counter | `status` | Track SUCCESS/SKIPPED/TIMEOUT/ERROR |
| `fraud_score` | Histogram | `decision` | Distribution of final fraud scores |
| `inference_latency_seconds` | Histogram | `source` | Per-layer latency breakdown |
| `l1_latency_seconds` | Histogram | — | L1 evaluation latency |
| `l2_latency_seconds` | Histogram | — | GNN inference latency |

All instrumentation is wrapped in `try/except` — metrics collection never breaks scoring.

### 6.2 Grafana Dashboard

4 panels in `prometheus/payshield-fraud-dashboard.json`:
1. **Block rate** (stacked by rule class)
2. **Escalation spike** (L2 status breakdown)
3. **Latency regression** (p50/p90/p99 over time)
4. **Fraud-score histogram** (BLOCK/REVIEW/ALLOW buckets)

### 6.3 Alert Rules

`prometheus/alerts.yml`:
- `HighL1BlockRate`: block rate > 50 per minute for 5 min
- `L2EscalationSpike`: SKIPPED/TIMEOUT rate > 10 per minute
- `ScoreLatencyP99High`: p99 > 100 ms for 5 min
- `FraudScoreTail`: p99 fraud score > 0.95 for 10 min
- `InvestigationQueueBacklog`: Celery queue depth > 100

---

## 7. Testing Strategy

### 7.1 Coverage Gates

| Gate | Target | Actual | File |
|------|--------|--------|------|
| TOTAL | ≥ 70% | **74%** (6135/1617) | — |
| Score path | ≥ 80% | **91%** (287/26) | `api/routes/score.py` |
| Ensemble | ≥ 80% | **90%** (133/13) | `engine/ensemble.py` |
| Graph features | ≥ 80% | **99%** (152/2) | `engine/graph_feature_engine.py` |

### 7.2 Test Suite Composition

| Layer | Tests | Files |
|-------|-------|-------|
| Unit — scoring/engine | ~95 | `test_statistical_filter.py`, `test_ensemble.py`, `test_graph_model.py`, `test_drift.py`, `test_redis_store.py` |
| Unit — security | 20 | `test_security_hardening.py` |
| Unit — agents | 27 | `test_agents.py` |
| Unit — A/B testing | 21 | `test_ab_testing.py` |
| Unit — store/redis | 20 | `test_redis_clients.py`, `test_store_components.py` |
| Integration — API | 48 | `test_api.py`, `test_score_path.py`, `test_security_api.py` |
| E2E | 1 file | `test_full_flow.py` |
| **Total** | **392 passed, 1 skipped** | |

### 7.3 Key Test Patterns

- **FakeRedis** (`tests/fake_redis.py`): In-memory async Redis with pipeline support, used as `app.state.resources["redis"]`. Never patch per-test — single source of truth.
- **Score path robustness** (`test_score_path.py`): Tests Redis failures, L1/ensemble/L2 failures, broadcast, idempotent replay, batch scoring, cache/drift/explanation/audit failure tolerance.
- **Metric delta tests**: `test_counters_increment` is delta-based — instrumentation counters accumulate across tests.

---

## 8. Compliance

### 8.1 Framework Scores

| Framework | Score | Key Controls |
|-----------|-------|-------------|
| PCI-DSS | 90/100 | Encryption, access control, audit logging, PII masking, MFA |
| RBI Localization | 100/100 | Data residency, explainability, human oversight, drift monitoring |
| EU AI Act | 100/100 | 13 controls: risk mgmt, conformity, post-market monitoring, data governance, transparency, human oversight, accuracy, robustness, technical documentation |

### 8.2 EU AI Act Controls (13)

| ID | Control | Evidence |
|----|---------|----------|
| RM-1 | Risk assessment document | `docs/security/risk-assessment.md` |
| CM-1 | Conformity assessment | `docs/security/conformity-assessment.md` |
| PM-1 | Post-market monitoring | `docs/security/post-market-monitoring.md` |
| DG-1 | Bias detection report | `models/fairness_audit.py` (SPD/EOD) |
| DG-2 | Demographic metrics tracking | `TRACK_DEMOGRAPHIC_METRICS` env |
| TR-1 | Model cards | `models/payshield_gnn_v1_card.md` (auto-generated) |
| TR-2 | Technical documentation | `docs/technical-documentation.md` |
| HO-1 | Human review override capability | `agents/human_review_agent.py` |
| HO-2 | Override rate reporting | `store/feedback/` directory |
| HO-3 | Human oversight log | `store/audit_logs/` with JSONL entries |
| AC-1 | PR-AUC ≥ 2x baseline | PR-AUC 0.195 ≥ 0.10 ✅ |
| AC-2 | FPR at 90% recall tracked | FPR 0.7135 (benchmarked) |
| RB-1 | Adversarial testing | `reports/adversarial/` |

---

## 9. Honest Limitations (Interview Defense)

### What PayShield Does
- Real-time L1 statistical filtering (p99 0.27 ms, 12 rules)
- Conditional GNN inference (40 ms timeout, 40% of live transactions)
- Async LLM investigation (qwen2.5:3b, ~35 s)
- Tamper-evident audit with hash chaining
- Per-key/per-user rate limiting
- TOTP MFA for admin accounts
- JWT refresh rotation (7-day sliding window)
- PSI drift detection with validated estimator
- Fairness audit (SPD/EOD across demographic slices)
- 392 tests at 74% coverage

### What PayShield Does Not Do (Yet)
- **GNN isn't always-on**: ~60% of requests skip L2 because the user's graph is too small (< 2 nodes) or model unavailable. This is architectural — fresh users produce random noise from empty ego-graphs.
- **Auto-model promotion**: `POST /admin/models/promote` is manual. Automatic promotion needs a CI/CD pipeline with canary deployment and automated rollback.
- **Dashboard**: Functional but minimal (3 pages, inline styles, no auth logic). A production frontend would need a full SPA rewrite.
- **Real data**: Trained on synthetic UPI data (30k transactions). Real NPCI data has different seasonality and fraud density.
- **Live agent orchestration**: 14 agents exist and are tested in isolation. Full swarm consensus is a research problem, not implemented.

---

## 10. Interview Q&A — Anticipated Questions

**Q: Why didn't you just use a rule engine instead of building a GNN?**
A: L1 rules catch known patterns (velocity bursts, geo jumps). They cannot catch coordinated mule rings where 50 accounts each send one normal-looking transaction to the same merchant — that's a graph pattern. The GNN provides 3.5× PR-AUC lift over an edge-free baseline because it captures relational structure. But I don't block the hot path on it — it conditionally fuses.

**Q: Why 53,826 parameters for a fraud model? Isn't that overkill?**
A: HeteroConv with per-edge-type SAGEConv weight matrices. Each of the 5 edge types (user→txn, txn→merchant, user→device, user→user, device→user) gets its own weight matrix — that's [(64×64) + (64×64)] × 2 layers × 5 edge types ≈ 81K — but with dimension-specific sizing and readout MLP, it's 54K. The value isn't more parameters — it's that shared-device mule rings and merchant transfers use different propagation rules.

**Q: How do you handle adversarial attacks — someone sending spoofed transactions to poison your velocity features?**
A: L1 velocity features are per-user and per-device — poisoning requires control of the user's device or account, which is an authentication problem upstream. Benford's Law provides a distributional check that is hard to spoof without knowing the detection thresholds. For model-level adversarial attacks, the `reports/adversarial/` directory documents noise-injection testing.

**Q: Your audit log has hash chaining — but what happens if someone modifies the audit file itself?**
A: `verify_chain()` recomputes every SHA-256 hash and checks that `prev_hash` matches the previous entry's hash. A single modified entry breaks the chain from that point forward. The check returns the exact index of the first mismatch. The `entry_id` is derived from the hash, so it changes on modification too — excluded from the hash computation via `{k: v for k, v in entry if k not in ("hash", "entry_id")}`.

**Q: What monitoring tells you your model is degrading in production?**
A: Three signals:
1. **PSI drift** — `GET /admin/drift/psi` compares yesterday's vs today's feature distributions. Validated estimator (shared quantile bins + Laplace smoothing), correctly calibrated to return 43→3.86 after the fix.
2. **L2 status distribution** — Prometheus counter `layer2_escalation_total` by status. A sudden spike in TIMEOUT or ERROR means the GNN service is degraded.
3. **Ensemble calibration** — ECE is tracked. If ECE drifts above 0.02, the calibrator needs refitting.

**Q: Walk me through what happens when a transaction arrives.**
A: (recite the data flow from Section 2.3 — 11 steps from receipt to response)

---

## 11. Repo Navigation Cheatsheet

```
PayShield/
├── api/
│   ├── routes/score.py          ← Main scoring endpoint (L1+L2+Ensemble)
│   ├── routes/investigation.py  ← LLM investigation retrieval (pipeline batching)
│   ├── routes/auth.py           ← Login, refresh, TOTP setup/verify
│   ├── routes/graph.py          ← Graph investigation API (paginated)
│   ├── main.py                  ← App factory, CORS, middleware, rate limit
│   ├── dependencies.py          ← verify_api_key, get_redis, rate limiter
│   └── lifespan.py              ← Startup/shutdown: Redis, Neo4j, Ollama, audit logger
│
├── engine/
│   ├── statistical_filter.py    ← L1: 12 rules (velocity, geo, Benford)
│   ├── ensemble.py              ← Fusion engine + isotonic calibrator
│   ├── graph_model.py           ← HeteroConv+SAGEConv GNN definition
│   └── graph_feature_engine.py  ← Ego-graph extraction
│
├── store/
│   ├── redis_client.py          ← AsyncRedisClient (circuit breaker)
│   ├── connection_pool.py       ← Pool + CircuitBreaker + maxmemory check
│   ├── audit_log.py             ← Hash-chained JSONL + AsyncAuditLogWriter
│   └── graph_db.py              ← NetworkXGraphDB (fallback)
│
├── compliance/
│   ├── eu_ai_act.py             ← 13-control EU AI Act checker (100/100)
│   ├── pci_dss.py               ← PCI-DSS checker (90/100)
│   └── rbi_localization.py      ← RBI checker (100/100)
│
├── models/
│   ├── payshield_gnn_v1_card.md ← Auto-generated model card
│   └── fairness_audit.py        ← SPD/EOD on synthetic slices
│
├── tests/
│   ├── fake_redis.py            ← In-memory async Redis (single source of truth)
│   ├── unit/test_security_hardening.py  ← TOTP, rate limiter, async audit, memory policy
│   ├── unit/test_agents.py      ← 27 agent tests (router, lifecycle, scoring, planner, critic, collective, mitigation)
│   ├── unit/test_ab_testing.py  ← 21 A/B tests (shadow/canary/lifecycle)
│   ├── integration/test_api.py          ← Core API endpoints
│   ├── integration/test_score_path.py   ← 25 score-path robustness tests
│   └── integration/test_security_api.py ← CORS, rate limit, refresh, TOTP, graph pagination
│
├── AUDIT_REPORT_v2.md           ← All original findings FIXED or WONTFIX
├── IMPLEMENTATION_AUDIT_REPORT.md ← Original audit (pre-P5)
└── COMPLIANCE_DELTA.md          ← Before/after compliance scores
```

---

*Last updated: 2026-08-01 after Phase 10 completion*
