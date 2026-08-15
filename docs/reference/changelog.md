# Changelog

## 2026-08-15 — GNN v1.1.0: Improved Model, Live Serving & Continuous Improvement

- **GNN v1.1.0 registered** (`models/registry/v1.1.0`, `latest` → v1.1.0): test PR-AUC **0.4125** (+108% vs v1.0.0's 0.198, 4.0× the edge-free MLP baseline 0.1028), AUC-ROC 0.7668, FPR@90% recall 0.4877, p99 0.70 ms CPU — winner picked by an 8-trial Optuna sweep (hidden 128, 3 layers, dropout 0.3, pos_weight 10, lr 4.3e-3, batch 16; 371,843 params)
- **Benchmark validation**: original v1.0 results archived (`models/gnn_benchmark_results_original.json`), delta report `models/gnn_benchmark_delta.md`, gate script `scripts/compare_benchmarks.py`
- **Architecture**: target-user readout with transaction attention (replaces global mean pooling); merchant dims 19 → 21 (shell flag, round-amount share), transaction dims 4 → 8 (inter-arrival gap, txn counts 5m/1h, distance from home centroid)
- **Live features**: `api/routes/score.py` computes inter-arrival gap + haversine location distance, maintains a Redis `FeatureCache` for merchant round-amount share; `GraphDBWriter` persists velocity/geo/round-share attrs onto graph nodes; the feature engine hydrates the target user first with `data.target_txn_n` bookkeeping
- **Checkpoint-driven serving**: `engine/graph_model.py.from_checkpoint()` + `ml/inference.py` rebuild the model from the artifact's own hyperparameters (weights_only=False for lazy params); fixed the P2P edge-type state-dict key (`transferred_to`)
- **Model registry**: `models/registry/v1.1.0/{model.pt, payshield_gnn_v1.pt, manifest.json, metadata.json, model_card.md}`; `models/registry/latest` symlink; `GET /admin/models/current` returns the promoted version's metadata
- **Drift monitoring from the feature registry**: six model features registered with `monitoring: true` (`configs/feature_registry.yaml`, `drift_key` aliases to the recorded zsets); `observability/drift.py` adds exact-value binning for binary/categorical features; `drift_report.py` reads thresholds + `min_samples` from `skew_detection`; `--config` flag on `scripts/run_drift_report.py`
- **Continuous improvement**: `make retrain` = full benchmark → `scripts/check_improvement.py` gate (epsilon 0.005 PR-AUC) → register + promote only on improvement; `configs/train_config_retrain.yaml`; `.github/workflows/retrain.yml` (weekly Monday 03:00 UTC + manual dispatch) opens a review PR for improved candidates
- 412 tests (344 unit + 68 integration)

## 2026-08-01 — Phase 10: Documentation & Compliance

- **EU AI Act: 100/100** (13 controls) — conformity assessment, post-market monitoring, human oversight logging, technical documentation
- **Fairness audit**: SPD/EOD on synthetic slices (gender, age-tier, city-tier) — `models/fairness_audit.py`
- **Model card**: auto-generated from benchmark JSON — `scripts/generate_model_card.py` → `models/payshield_gnn_v1_card.md` (zero hand-edited metrics)
- **AUDIT_REPORT_v2.md**: all original findings triaged FIXED (14 resolved in P5-P10) or WONTFIX
- **README**: Implementation Status table (L1/L2/L3/ops/auth/compliance/audit), honest conditional fusion wording, EU AI Act 100/100
- 392 tests, 74% coverage (gates: score 91%, ensemble 90%, graph 99%)

## 2026-08-01 — Phase 9: Security Hardening & Performance

- **CORS**: `allow_origins` from `FRONTEND_URL` env (no wildcard)
- **Rate limits**: per-API-key 1000 req/hr + per-user via Redis incr+TTL; 429 with Retry-After
- **JWT refresh rotation**: fixed revocation bug (storing raw token instead of jti); login uses 7-day sliding window (`REFRESH_TOKEN_EXPIRE_DAYS`)
- **TOTP MFA**: RFC 6238 (SHA-1, 30s step, 6 digits, pure stdlib); `/auth/totp/setup` + `/auth/totp/verify` admin-only endpoints
- **Async audit logger**: `asyncio.Queue` + background worker (flush every 1s or 100 entries); <1ms hot-path append
- **Investigations pipeline**: MGET batching (1 round trip instead of N)
- **Redis maxmemory check**: `ensure_memory_policy` warns on non-`allkeys-lru` config
- **Graph pagination**: limit/offset with `has_more` flag on `get_entity_network`
- **verify_chain() fix**: was including `entry_id` in hash recomputation, causing all verifications to fail
- 39 new tests (20 unit, 19 integration)

## 2026-08-01 — Phase 7 & 8: A/B Testing & Multi-Agent Coverage

- **A/B testing** (Phase 7): 21 tests — shadow/canary registration, lifecycle, statistical evaluation, guardrails, rule shadow mode
- **Experiments API**: process-level framework singleton fix (experiments persisted across requests)
- **Agents** (Phase 8): 27 tests — message router, base lifecycle, transaction scoring, planner decomposition, critic challenge logic, collective fusion, mitigation execution/pending-confirmation/rollback

## 2026-08-01 — Phase 6: Prometheus + Grafana Observability

- **Hot-path instrumentation**: `_observe_l1_block`, `_observe_ensemble` (try/except-guarded — metrics never break scoring)
- **Prometheus**: `prometheus/prometheus.yml` + `prometheus/alerts.yml` (5 alert rules)
- **Grafana**: `prometheus/payshield-fraud-dashboard.json` (4 panels) + provisioning

## 2026-08-01 — Phase 5: Coverage Gates & Robustness

- **Coverage gates met**: TOTAL 74%, score.py 91%, ensemble.py 90%, graph_feature_engine.py 99%
- **Drift fix**: PSI estimator — shared quantile bins + bin-count scaling + Laplace smoothing (43.4 → 3.86)
- **25 score-path robustness tests**: Redis failures, L1/ensemble/L2 failures, broadcast, idempotent replay, batch scoring
- 302 passed, 1 skipped

## 2026-07-31 — Phase 4: Ensemble Calibration & Model Training

- **Isotonic calibrator fitted**: `models/production/calibrator_v1.pkl`, ECE 0.055 → 0.010. Above-support passthrough for high-confidence scores.
- **GNN benchmark**: `scripts/benchmark_gnn.py` → `models/gnn_benchmark_results.json` — PR-AUC 0.195 (3.8× vs edge-free MLP 0.052), AUC-ROC 0.667, per-ego-graph inference p99 0.43 ms (CPU)
- **Model card corrected**: AUC > 0.92 claim replaced with measured numbers; params 53,826 (not ~15K); latency p99 2.5 ms (not < 50 ms)

## 2026-07-31 — Phase 3: L2 GNN Conditional Fusion

- **L2 wired into live path**: `_run_l2_inference` replaces the `type("L2",...)()` stub
- **Five status codes**: SUCCESS, SKIPPED_NO_GRAPH (< 2 nodes), TIMEOUT (> 40 ms), MODEL_UNAVAILABLE, ERROR
- **L1-only fallback**: ensemble weight drops to L1-only on any non-SUCCESS status
- Ego-graph extraction via `engine/graph_feature_engine.py` (live, per-request)

## 2026-07-31 — Phase 2: End-to-End Validation & Compliance Hardening

- **PCI-DSS 60 → 90, RBI 16 → 100** (both passing) — see `COMPLIANCE_DELTA.md`
- **Tamper-evident audit log**: `store/audit_log.py` — hash-chained JSONL with PII masking
- **18 bugs fixed**: startup crash, canned score results, worker boot failure, LLM JSON parser, RBAC gaps, Docker build, PSI estimator, drift sampling, synthetic generator crashes, and more

## 2026-07-31 — Phase 1: Core Infrastructure

- FastAPI application (11 route modules)
- L1 statistical filter (12 configurable rules: velocity, geo, Benford)
- Redis feature store with circuit breaker
- Celery worker for async LLM investigations
- React dashboard (Vite+React skeleton)
- Docker Compose stack (5 services)
- Synthetic UPI data generator
- K8s manifests (16 base manifests)

## v1.0.0 (2026-07-28)

- Initial system architecture and component scaffolding
- Feature engineering pipeline (Redis-backed velocity/geo/Benford features)
- L1 statistical filter with 12 configurable rules
- Ensemble fusion engine with weighted blending + isotonic calibration
- LLM investigation agent with structured prompts (Celery + Ollama)
- 14-agent framework (12 concrete agents + MessageRouter + OrchestratorState)
- FastAPI factory with middleware stack (CORS, timing, security headers, rate limit)
- JWT authentication + API Key verification
- Transaction scoring API (REST + batch, up to 100)
- Investigation, feedback, compliance, graph, admin, experiments endpoints
- WebSocket server + SSE for real-time alert streaming
- PostgreSQL schema + Alembic migrations
- React dashboard scaffolding (3 pages)
- K8s manifests, DR runbooks, SRE documentation
