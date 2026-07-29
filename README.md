# PayShield — Post-Mortem Audit

> **Date:** 2026-07-29  
> **Scope:** Full codebase audit of the entire project  
> **Format:** Brutally honest accounting of what exists vs. what works

---

## The Good

The architecture document and code layout are excellent. The system envisions a genuinely impressive fraud detection pipeline:

- **Multi-layer scoring:** Statistical filters → GNN → Ensemble → LLM investigation → Multi-agent orchestration
- **~130 source files** across well-organized modules: `api/`, `engine/`, `agents/`, `llm/`, `store/`, `compliance/`, `ml/`, `observability/`
- **Complete multi-agent framework** with 8 agents (Planner, Profile, Transaction, Collective, Critic, Validation, Mitigation, Memory, HumanReview, Monitoring, Reflection)
- **Docker Compose** for 5 services (api, worker, redis, ollama, dashboard)
- **24 unit tests**, integration tests, e2e tests, and a Locust load test
- **Compliance stubs** for PCI-DSS, RBI, and EU AI Act
- **Prometheus metrics**, structured logging, circuit breaker for Redis
- **YAML-driven configuration** for rules, features, RBAC

---

## The Bad

### 1. The Scoring Route Is Broken (Critical)

The hottest path in the system — `POST /v1/score` — cannot execute a single request:

| File | Line | Bug |
|------|------|-----|
| `api/routes/score.py` | 39, 44 | `redis.get()` called synchronously on an async Redis client |
| `api/routes/score.py` | 53 | `stat_filter.evaluate()` called without `await` (method is async) |
| `api/routes/score.py` | 77 | `ensemble.fuse()` called without `await` on an async resource |

Every scoring request would throw a `TypeError` or `RuntimeWarning` about a never-awaited coroutine.

The same pattern infects the entire API layer:

| File | Lines | Bug |
|------|-------|-----|
| `api/routes/investigation.py` | 22, 59, 64 | Synchronous `redis.get()` / `redis.keys()` |
| `api/routes/admin.py` | 29, 112 | Synchronous `redis.set()` / `redis.get()` |
| `api/routes/feedback.py` | 24, 41, 43, 80 | Synchronous Redis calls throughout |
| `api/routes/health.py` | 18 | Synchronous `redis.health_check()` |
| `api/lifespan.py` | 18 | Synchronous `redis.health_check()` during startup |

**All Redis operations across the API layer are broken.** Someone wrote async Redis client code but used await-free synchronous call syntax everywhere.

### 2. Tests Don't Match the Code (High)

The test suite tests interfaces that don't exist:

| Test File | Imports | Actual Class in Codebase |
|-----------|---------|--------------------------|
| `tests/unit/test_statistical_filter.py` | `StatisticalResult` | Class doesn't exist — uses `FilterResult` / `Layer1Result` |
| `tests/unit/test_statistical_filter.py` | `StatisticalFilter.evaluate(txn, store)` | Actual signature: `evaluate(velocity_features, deviation_features, ...)` — completely different |
| `tests/unit/test_statistical_filter.py` | `benford_expected_distribution` from `data.features.benford` | Module `data/features/benford` may not exist (actual Benford code in `engine/statistical_filter.py`) |
| `tests/unit/test_ensemble.py` | `EnsembleScorer` | Class doesn't exist — uses `EnsembleFusionEngine` |
| `tests/unit/test_ensemble.py` | `StatisticalResult` | Same as above |
| `tests/unit/test_schemas.py` | `TransactionEvent`, `InvestigationReport` | Classes don't exist — uses `ScoreRequest`, `InvestigationReportResponse` |
| `tests/unit/test_graph_db.py` | `GraphDB.add_node()` / `.add_edge()` / `.get_ego_graph()` | All three methods are stubs (body is just `pass`) — tests pass vacuously |

**~70% of unit tests pass for the wrong reasons** — they test APIs that don't exist in the actual codebase, or test stubs that do nothing.

### 3. Compliance Modules Are Stubs (High)

The compliance route in `api/routes/compliance.py` imports:

- `compliance.pci_dss.PCIDSSComplianceChecker`
- `compliance.rbi_localization.RBILocalizationChecker`
- `compliance.eu_ai_act.EUAiActComplianceChecker`
- `compliance.audit_generator.ComplianceAuditGenerator`
- `compliance.evidence_collector.EvidenceCollector`

These files exist but only define class shells without real compliance logic. Every endpoint would raise a 500 error or return empty/meaningless data. The compliance feature is non-functional.

### 4. Reflection Agent Is Inert (Medium)

`agents/reflection_agent.py:151` — `_get_feedback_data()` unconditionally returns `[]`. This means the entire reflection analysis pipeline (FP clustering, new-user bias detection, salary-day analysis, agent performance analysis) produces zero findings. The agent runs but discovers nothing.

### 5. No Trained Model (Medium)

The `models/` directory contains:
- `.gitkeep`
- `payshield_gnn_v1_card.md` (a model card with no actual model)
- `calibration/` (empty — no calibrator pickle)

The `ml/` module has training infrastructure (`train.py`, `registry.py`, `model.py`) but there's no evidence of a trained GNN checkpoint or calibration artifact. The system would attempt inference through the GNN layer and silently degrade into no-ops.

### 6. Duplicated and Dead Code (Low-Medium)

| Issue | Detail |
|-------|--------|
| `GeoPoint` dataclass | Defined in both `api/schemas.py:7` and `engine/statistical_filter.py:149` |
| Benford's Law logic | Module-level functions in `engine/statistical_filter.py:239-253` duplicate what may exist in `data/features/` |
| `store/graph_db.py` | Full of `pass` stubs — the actual graph DB logic lives in `data/graph_builder.py` and `engine/graph_builder.py` |
| Hardcoded API key | `"payshield-dev-key-2026"` in `api/dependencies.py:23` |
| `tasks/investigation_task.py` | Celery task imports async Redis — this is called from sync Celery worker context |

### 7. WebSocket Alerts Not Pushed

`api/routes/stream.py` sets up a WebSocket endpoint (`/v1/stream`) where clients can subscribe, and uses the `ConnectionManager` from `api/websocket.py`. However, **no component in the system ever calls `manager.broadcast()`** — the WebSocket accepts connections and responds to pings/subscribes, but never pushes alert data.

---

## The Ugly

### Architecture vs. Reality

| Claimed In README | Actual State |
|-------------------|--------------|
| "p50 < 30 ms inference latency" | Pipeline is broken — 0 ms because no request completes |
| "AUC-ROC > 0.92" | No trained model exists to measure |
| "FP rate < 5% @ 0.90 recall" | No calibration data, no evaluation pipeline |
| "60-phase implementation complete" | Core integration path (API → Engine → Redis) has await bugs |
| "PCI-DSS / RBI compliance" | Compliance modules are stubs returning no data |
| "Multi-agent orchestration" | Agents exist but none are wired into the API request path |

### What Was Produced

The project successfully created **a large, well-structured directory layout** and a convincing architecture document. The module boundaries, class hierarchies, configuration files, and Docker setup all signal a production-grade system. The code is well-formatted, uses modern Python (3.11+), Pydantic v2, FastAPI, PyTorch Geometric, and follows good naming conventions.

The `data/synthetic_upi.py` generator is genuinely impressive — it produces realistic UPI transaction data with mule rings, burst attacks, merchant collusion, and account takeover scenarios, including geospatial jitter and temporal patterns.

The `engine/statistical_filter.py` has a well-designed VelocityFilter (6 rules), GeoSpatialFilter (4 rules), and BenfordFilter (2 rules) with configurable decision gates and shadow mode.

The `agents/` framework is properly abstracted with BaseAgent, MessageRouter, AgentState, and priority-based message queues.

### What Was NOT Produced

1. **A working `POST /score` endpoint** — the primary entry point is broken by trivial async/await bugs
2. **Tests that validate actual code** — the test suite would catch none of the real bugs
3. **A trained model** — the GNN layer is infrastructure without a payload
4. **Functional compliance** — regulatory modules are named but empty
5. **Working WebSocket alerting** — the stream endpoint connects but never sends data

---

## File Inventory

| Directory | Files | Est. Lines | Verdict |
|-----------|-------|------------|---------|
| `api/` | 12 | ~900 | All Redis calls lack await — broken |
| `api/routes/` | 10 | ~950 | Broken (async/sync mismatch) |
| `engine/` | 8 | ~1,600 | Well-designed, unused due to API bugs |
| `agents/` | 15 | ~1,800 | Complete framework, not wired into request path |
| `store/` | 15 | ~1,400 | Solid, but called synchronously from API |
| `llm/` | 9 | ~500 | Functional, behind Celery |
| `compliance/` | 7 | ~700 | Stubs only |
| `ml/` | 8 | ~600 | Training infrastructure present, no artifacts |
| `data/` | 5 | ~550 | Strong synthetic data generation |
| `observability/` | 4 | ~60 | Minimal but functional |
| `configs/` | 6 | ~400 | YAML-driven, well factorized |
| `tests/` | 20 | ~1,100 | Low value — test wrong interfaces |
| Root config | 8 | ~200 | Adequate |
| **Total** | **~130** | **~12,000** | **Solid skeleton, broken integration** |

---

## Priority Fix List

1. **Add `await` to every Redis call in `api/routes/*.py`** and `api/lifespan.py` (15+ sites)
2. **Add `await` to `stat_filter.evaluate()`** and `ensemble.fuse()` in `api/routes/score.py`
3. **Realign test suite** — update tests to match actual `FilterResult`/`EnsembleFusionEngine`/`ScoreRequest` interfaces
4. **Either implement or remove** compliance checkers (`pci_dss.py`, `rbi_localization.py`, `eu_ai_act.py`)
5. **Wire WebSocket alert pushing** into the score route for BLOCK/REVIEW decisions
6. **Train or scaffold** a real GNN checkpoint and calibrator
7. **Fix `ReflectionAgent._get_feedback_data`** to actually query stored feedback
8. **Remove duplicated `GeoPoint`** — consolidate into one canonical definition
9. **Move hardcoded dev API key** to environment variable with a sensible default
10. **Add `requirements.txt` or lockfile** for reproducible builds

---

## Quick Start (Will Not Work)

```bash
docker compose -f docker/docker-compose.yml up
# ^ The API will start but /v1/score returns 500
```

## License

MIT

---

**Purvansh Sahu** — IIT Madras ML Researcher (4th Year) · Scaler · BITS Pilani  
[purvanshsahu.site](https://purvanshsahu.site)
