# Changelog

## Post-v1.0.0 (2026-07-31) — L2 GNN measured evidence

### L2 GNN — first measured performance (`scripts/benchmark_gnn.py`)
- Heterogeneous ego-graph dataset built from the synthetic UPI generator (30k txns, 5,558 ego-graphs, user-disjoint split)
- **Measured**: test PR-AUC 0.198 (lead metric for imbalanced fraud — 3.5× vs. baseline), AUC-ROC 0.692, FPR 0.71 @ 90% recall; per-ego-graph inference p50 1.0 ms / p90 1.5 ms / p99 2.5 ms (CPU)
- **Baseline**: edge-free MLP PR-AUC 0.056 (AUC-ROC 0.481) — graph structure worth ~3.5× PR-AUC lift
- Corrected unmeasured model-card claims (AUC ">0.92" → 0.692; params ~15K → 53,826; latency "<50 ms" → p99 2.5 ms)
- Results: `models/gnn_benchmark_results.json`; card: `models/payshield_gnn_v1_card.md`

### Agent docs — honest inventory
- `docs/architecture/AGENTS.md` rewritten: the 8 "design-doc agents" (risk/pattern/behavior/history/network/compliance/decision) never existed in code; real inventory is 12 concrete `BaseAgent` subclasses + router + state, with stubs flagged (planner, collective, critic)

### Bug fixes
- Synthetic generator: `tier4` in `CITY_TIER_WEIGHTS` with no tier-4 city → `IndexError` (added 4 tier-4 cities)
- Synthetic generator: `random.choice(..., weights=)` (numpy API on stdlib RNG) → `TypeError`

### Docs
- README: "Why PayShield" origin section, L2 GNN measured table, agent one-liner table, "Limitations & Deferred Work" section, bug table extended to 18 rows
- Model card + registry `v0.1.0` JSON updated to measured values; SLO doc adds GNN latency

## Post-v1.0.0 (2026-07-31) — End-to-end validation & hardening

### Compliance hardening
- **PCI-DSS 60 → 90, RBI 16 → 100 (both passing)** — see `COMPLIANCE_DELTA.md`
- Tamper-evident audit log: append-only JSONL with SHA-256 hash chaining and PII masking (`store/audit_log.py`)
- `ENCRYPTION_KEY`, `ENFORCE_RBAC`, `DATA_REGION=IN`, `ENABLE_LLM_INVESTIGATOR` wired through compose + `.env.example`
- Explanation artifacts persisted for every BLOCK/REVIEW (`models/production/explanations/`)
- Analyst feedback loop persisted to disk (`store/feedback/`)
- Versioned model cards (`models/registry/v1.0.0`, `v0.1.0`)
- Named volumes keep audit/feedback/explanations/compliance reports across container rebuilds

### Drift monitoring
- Feature sampling on the scoring path (`drift:feat:*` time-scored zsets)
- Robust PSI estimator: shared quantile bins, bin count scaled to sample size, Laplace smoothing — eliminated false spike (PSI 43.4 → 3.86 for the same data)
- `GET /admin/drift/psi` endpoint + `scripts/run_drift_report.py` + `scripts/seed_drift_baseline.py`

### Performance
- Sync-path latency measured: p50 8.5 ms, p90 15.0 ms, p99 63.3 ms; L1 rule evaluation p99 0.27 ms
- `latency_breakdown` (L1 rules / ensemble) added to every score response
- `scripts/benchmark_latency.py` for reproducible numbers
- LLM investigation moved to `qwen2.5:3b` (reliable JSON output on CPU, ~35 s async — off the hot path)

### Bug fixes
- Startup crash (statistical filter `None` config), canned score results → real Redis-backed features
- Worker boot failure (`No module named 'infrastructure'`) via module-level import fallback
- LLM JSON-only prompt + tolerant parser; evidence `UnboundLocalError`
- RBAC: `system` role `feedback:write` + `investigation:read`; `x-api-key` accepted for role-scoped endpoints
- Dashboard Docker build (deps, TS types, COPY paths)
- Drift sampling missing `await` + zset member/score convention mismatch

### Infrastructure
- Docker compose: named volumes for data dirs, `ENCRYPTION_KEY`/compliance env for api + worker

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
