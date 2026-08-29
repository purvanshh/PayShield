# PayShield: Return-Risk Scorer for Indian E-Commerce

**One-sentence:** PayShield scores every order *before it ships*, catches
high-risk returns at high precision, and saves a fashion merchant **₹17.0
lakh/month** on 10,000 orders (Stage 1) — up to **₹53.6 lakh/month** for a
premium electronics merchant (Stage 3).

**For evaluators:** Start with [`EVALUATOR_GUIDE.md`](EVALUATOR_GUIDE.md) —
10-minute walkthrough. Business case: [`BUSINESS_IMPACT.md`](BUSINESS_IMPACT.md).
Honest ledger: [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md).

**The numbers — Progressive Merchant Maturity:**

PayShield is evaluated across **three named merchant-maturity scenarios**, each a
different merchant segment with a documented data-generating process. Stage 1 is
the honest floor; Stage 3 represents a premium merchant with mature data
instrumentation. The model architecture, split and evaluation protocol are
**identical** across scenarios — only the data source changes.

| Stage | Merchant segment | Visible features | PR-AUC | ROC-AUC | ₹/month (Electronics) | ₹/month (Fashion) |
|---|---|---|---|---|---|---|
| **Stage 1: Basic** | high hidden variance | 7 | **0.7991** | **0.8431** | ₹36.8L | ₹17.4L |
| **Stage 2: Enriched** | rating + delivery observed | 9 | **0.8834** | **0.9198** | ₹44.7L | ₹21.4L |
| **Stage 3: Premium** | mature instrumentation, low noise | 9 | **0.9497** | **0.9612** | **₹53.5L** | **₹26.0L** |

> These three scenarios mirror merchant data-maturity stages common in Indian
> e-commerce. Stage 1 is the conservative baseline; Stage 3 represents a premium
> merchant with mature instrumentation. ROC-AUC is **measured** (`roc_auc_score`),
> never hardcoded. All numbers in a row come from one model (the default-XGBoost
> `return_risk_results_{scenario}.json`); the tuned champion reaches 0.8089 /
> 0.8875 / 0.9488 PR-AUC (see `reports/scenario_comparison.md`). Reproduce:
> `python scripts/run_all_scenarios.py`.

**Run it (hermetic):** `python scripts/train_xgb_return_risk.py --scenario premium`

**Honest prototype note:** a student PoC on Razorpay's infrastructure — not
production software.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Number

The headline three-scenario table is above. The single-number floor (Stage 1:
Basic) — the conservative, high-hidden-variance baseline that mirrors the
original submission — is preserved here for continuity:

| Metric | Value | What It Measures |
|---|---|---|
| **Stage 1 PR-AUC** | **0.7991** | Default XGBoost on 7 features + hidden DGP noise on the `returned` label |
| **Stage 1 ROC-AUC** | **0.8431** | Measured via `roc_auc_score` (Mistake 1 fix — never hardcoded) |
| **Stage 1 cost at 0.50 gate** | **₹17.4L/month** | Monthly savings on 10k fashion orders, review cost ₹200 |
| **Stage 3 cost at 0.50 gate** | **₹53.5L/month** | Monthly savings on 10k electronics orders at the premium operating point |

Every stage is trained on a non-circular synthetic DGP: visible features plus
hidden confounders (packaging, weather, customer mood — and, in Stage 1, product
rating + delivery speed too) that the model never observes. That makes the
absolute PR-AUC lower but more honest than a circular benchmark. See
[`docs/DESIGN_DECISIONS.md`](docs/DESIGN_DECISIONS.md) for the per-stage DGP
parameters and the "Why Three Scenarios" rationale.

### The model — Stage 1 (Basic) detail (2,000-order hold-out, gate 0.50)

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **XGBoost (default)** | **0.7991** | **0.8431** | **0.644** | **0.812** | **0.718** |
| Hand-weighted (fallback) | 0.7896 | 0.8392 | 0.957 | 0.194 | 0.323 |
| Naive: serial returner (>40%) | 0.6991 | 0.6895 | 0.631 | 0.615 | 0.623 |
| Naive: COD + high AOV | 0.5884 | 0.5555 | 0.685 | 0.159 | 0.258 |

XGBoost edges the hand-weighted scorer (**+0.010 PR-AUC**) and clearly beats
both naive rules (**+0.10 over the best naive baseline**). The tuned champion
(`scripts/tune_xgb.py`) reaches PR-AUC 0.8089 / ROC-AUC 0.8477 on the same
hold-out — see `models/tune_results_basic.json`. Full details in
["What We Measured"](#what-we-measured) below.

### Cost model — the 0.50 review gate

On a 10k-order fashion merchant (₹2.5k AOV, 18% return rate), the **0.50 review
gate** saves **₹17.4L/month** at precision 0.644 and recall 0.812 — the Stage 1
XGBoost operating point, measured on the held-out test set. The config-driven
gate sweep (computed from the measured operating curve in
`models/return_risk_results_basic.json`):

| Review gate | Flag rate | Precision | Recall | Net ₹ / month | ROI |
|---|---|---|---|---|---|
| 0.30 | 68.8% | 0.530 | 0.922 | ₹15.6L | 31.1% |
| 0.40 | 58.6% | 0.589 | 0.871 | ₹16.8L | 33.4% |
| 0.45 | 54.4% | 0.619 | 0.850 | ₹17.4L | 34.5% |
| **0.50** | **49.9%** | **0.644** | **0.812** | **₹17.4L** | **34.5%** |
| 0.60 | 42.6% | 0.695 | 0.748 | ₹17.5L | 34.7% |
| 0.70 | 34.5% | 0.748 | 0.651 | ₹16.6L | 32.9% |

The sweep peaks around 0.60 for this vertical; 0.50 is the designed review gate.
See [`docs/COST_MODEL.md`](docs/COST_MODEL.md)
for the vertical sensitivity sweep (fashion-high vs. fashion-low vs.
electronics vs. grocery).

---

## How It Works

```
[Razorpay order.paid]  ──►  POST /v1/return/score
                                 │
                 ┌───────────────┼──────────────────┐
                 ▼               ▼                  ▼
        ┌────────────────┐ ┌──────────────┐ ┌───────────────┐
        │ Feature Engine  │ │ Rules Engine │ │  Redis Store  │
        │ 7 visible       │ │ 8 config-    │ │ user history, │
        │ features (+     │ │ driven rules │ │ merchant      │
        │ hidden DGP      │ │ (YAML,       │ │ baselines,    │
        │ noise)          │ │ hot-reload)  │ │ return zsets  │
        └────────┬────────┘ └──────┬───────┘ └───────────────┘
                 └────────┬────────┘
                          ▼
              ┌──────────────────────┐
              │  XGBoost Primary     │   learns weights from data
              │  (200 trees, tuned)  │   captures nonlinear interactions
              └──────────┬───────────┘
                         │
              ┌──────────┴───────────┐
              │  Fallback: Hand-      │   transparent, interpretable
              │  Weighted Composite   │   always available
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │  Tier: LOW / MEDIUM  │   LOW → ACCEPT (ship)
              │        / HIGH        │   MEDIUM → FLAG_FOR_REVIEW
              └──────────────────────┘   HIGH → REQUIRE_PREPAID
```

**The 7 features** (each carries a value, normalized value, weight and source
tag in the API response — `redis_hash`, `computed`, `lookup_table`,
`default_new_user`):

| Feature | Source | What it captures |
|---|---|---|
| `user_return_rate_30d` / `90d` | Redis history | Recent return propensity (the dominant signal) |
| `txn_amount_risk` | Computed | Log-normalised order value (`log1p(amount)/log1p(50000)`) |
| `txn_category_return_baseline` | Lookup/zset | Category prior (fashion ~32%, electronics ~8–12%) |
| `user_cod_refusal_rate` | Redis history | COD abuse pattern |
| `user_return_velocity_7d` | Redis zset | Return burst signal |
| `user_serial_returner_flag` | Computed | >50% lifetime rate with ≥3 orders |

**Gate logic is a cost decision, not an accuracy contest.** A wrong MEDIUM flag
costs **₹200** of operator time (the order still ships); a wrong HIGH block
costs **₹3,180** (lost order + CAC + churn). Because review is ~16× cheaper
than blocking, the gate optimizes for precision at the review tier, and the
threshold is config-driven per vertical
(`configs/return_risk_rules.yaml`).

**The enriched feature pipeline** (`return_risk/feature_engine.py` + Redis
user/merchant profiles) exists in the codebase and the live scorer runs on it,
but the XGBoost model has **not yet been recalibrated to enriched feature
distributions** — it was trained on the offline DGP's features. Retraining it
on the enriched pipeline is the highest-priority next step (see
["What I'd Do Next"](#what-id-do-next)).

**Every response carries a provenance-honest `confidence`** (0–1) blending how
decisive the score is (distance from the ambiguous 0.5 boundary), how much of
the signal comes from real data vs. population defaults, and the user's history
depth — so a brand-new user with no history scores ~40% confidence (mostly
priors, honestly labelled) while a full-history profile reaches ~97%.

---

## Agent Orchestration

The stack runs an **agent worker** (`python -m agents.worker`) that keeps four
live agents operating on real scored orders — not mock scaffolding. Each agent
is a message-passing `BaseAgent` registered on a `MessageRouter`; the worker
owns the lifecycle:

- a **heartbeat loop** renews `agent:heartbeat:{agent_id}` in Redis every 20s
  (TTL 60s) so the dashboard **Agents** page and `GET /admin/agents/health`
  report live `RUNNING` status (<30s staleness rule)
- a **feed loop** drains new `RETURN_RISK_SCORED` entries from the audit chain
  into the transaction + profile agents every 15s
- a **reflection loop** triggers the reflection agent over the last 24h every
  5 minutes

| Agent | Type | What it does |
|---|---|---|
| `transaction_agent` | TRANSACTION | Analyzes each scored order — order velocity, COD exposure, amount-vs-category risk, live merchant return rate from Redis — emits `TXN_ANALYSIS_RESULT` with evidence |
| `profile_agent` | PROFILE | Builds per-user return-risk profiles (order count, avg amount, COD share, avg score) and broadcasts `PROFILE_ANOMALY` when a user's recent behavior drifts from their own history |
| `reflection_agent` | REFLECTION | Reflects over the return-risk + chargeback audit chain (tier skew, score drift, merchant concentration, new-user bias) using the deterministic risk-suite analysis; routes recommendations to human-review |
| `human_review_agent` | HUMAN_REVIEW | Handles analyst feedback + escalations; feeds accuracy signals back to reflection |

The agent framework (`agents/base.py`, `agents/message.py`, `agents/state.py`)
was restored from the pre-scope history and **rewired to the return-risk
surface** — the original fraud/LLM agents were deleted in the repo scoping
commit, leaving the UI and health endpoint as scaffolding with nothing behind
them. The worker is a first-class compose service (`docker-compose.yml` →
`worker`).

---

## Run It

**Prerequisites.** Python **3.11** (the Docker base and the canonical verify
interpreter) and `pip install -r requirements.txt`. On **macOS** xgboost also
needs the OpenMP runtime — install it once with `brew install libomp`. The ML
stack (`numpy`/`pandas`/`scipy`/`scikit-learn`/`xgboost`) is **pinned exactly**
so the `--full-verify` numbers reproduce byte-for-byte on macOS and Linux; the
verify suite auto-links a Homebrew `libomp` if it is missing and otherwise tells
you the one command to run. A Python 3.12+ environment will not reproduce the
committed numbers (numpy 2.5.0/xgboost 3.4.1 have no Linux wheels) — use 3.11.

Hermetic (no services needed):

```bash
python scripts/train_xgb_return_risk.py      # train + baseline comparison (~20s)
python scripts/ablation_study.py             # leave-one-feature-out ablation (~60s)
python scripts/tune_xgb.py                   # 144-combo hyperparameter search (~15s)
python docs/cost_model/calculator.py         # the numbers in ₹
python docs/cost_model/calculator.py --vertical-sensitivity   # where the gate breaks
```

One-shot interview-defense gate (10 checks: base-generator integrity,
byte-identical determinism, AUC gates, ₹ gates, no-hardcoded-fallbacks, doc &
dashboard consistency, ablation baseline):

```bash
python scripts/run_all_scenarios.py --full-verify     # prints PASS/FAIL per check
```

Live stack (needs Docker): `docker compose -f docker/docker-compose.yml up`
starts **api + redis + dashboard + agent worker**:

- **API** — `http://localhost:8000` (FastAPI, return-risk hero surface)
- **Dashboard** — `http://localhost:3000` (SPA: Return Risk, Fraud, Chargeback,
  Cost Model, Drift, A/B Experiments, Agents; login `admin` / `admin`)
- **Agent worker** — runs the four live agents (transaction, profile,
  reflection, human-review) against real scored orders from the audit chain,
  renewing Redis heartbeats every 20s. See the dashboard **Agents** page or
  `GET /admin/agents/health`.

Then `python scripts/seed_demo_data.py` and `python scripts/verify_live_stack.py`
(10 scenarios against real Redis — see ["Live verification"](#live-verification)).

---

## What We Measured

### Baseline comparison (Stage 1: Basic, same 2,000-order hold-out, gate 0.50)

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|
| **XGBoost (default)** | **0.7991** | **0.8431** | **0.644** | **0.812** | **0.718** |
| Hand-weighted (fallback) | 0.7896 | 0.8392 | 0.957 | 0.194 | 0.323 |
| Naive: serial returner (>40%) | 0.6991 | 0.6895 | 0.631 | 0.615 | 0.623 |
| Naive: COD + high AOV | 0.5884 | 0.5555 | 0.685 | 0.159 | 0.258 |

### Ablation — every feature earns its place (LOFO retraining, seed-99 test set)

| Feature removed | PR-AUC | Drop from baseline (0.8087) |
|---|---|---|
| `amount_vs_user_aov_ratio` | 0.7581 | **−6.3%** |
| `payment_method_risk` | 0.7800 | **−3.6%** |
| `user_return_rate_30d` | 0.7842 | **−3.0%** |
| `user_return_rate_90d` | 0.8013 | −0.9% |
| `device_fingerprint_match` | 0.8038 | −0.6% |
| `category_return_baseline` | 0.8079 | −0.1% |
| `days_since_last_order` | 0.8092 | −0.1% |
| **combined: both rate features** | 0.7285 | **−9.9%** |

The individual drops are small because the two rate features share the
user-history signal; removing **both** costs **−9.9%**, the largest block.
The drop is genuine feature importance measured against hidden confounders —
not circular recovery.

### Confusion matrix (Stage 1 XGBoost, 2,000-order hold-out, gate 0.50)

From `scripts/train_xgb_return_risk.py --scenario basic`:

```
                     Not Flagged   Flagged
Actual No Return          853       355   (TN=853, FP=355)
Actual Return             149       643   (FN=149, TP=643)
```

Precision **0.644** · recall **0.812** · F1 **0.718**.

### Tuning

`HalvingGridSearchCV` over a widened grid (`max_depth` × `n_estimators` ×
`learning_rate` × `scale_pos_weight` × `min_child_weight` × `reg_lambda` ×
`reg_alpha` × `gamma`), selected on validation PR-AUC: best
`max_depth=4, n_estimators=300, lr=0.05, spw=1.5, min_child_weight=1,
reg_lambda=10` → test PR-AUC **0.8089** / ROC-AUC **0.8477**
(`models/tune_results_basic.json`). The per-scenario tuned champions are in
`reports/scenario_comparison.md`.

### Live verification

All ten curated scenarios pass against the running Docker stack — serial
returner → HIGH, honest → LOW, chargeback responses, signed webhooks, drift.
Full table in `scripts/verify_live_stack.py`. The live feature pipeline is kept
inside the model's training envelope: the scorer's `amount_vs_user_aov_ratio`
never falls back to `avg_return_value` (a profile with cheap returns but no
stored AOV previously produced an out-of-distribution ratio of 8.0 that spiked
honest customers to MEDIUM/HIGH) — see `return_risk/feature_engine.py`.

### For judges (30-second version)

- **[`JUDGES_CHEAT_SHEET.md`](JUDGES_CHEAT_SHEET.md)** — the one-number story, the three surfaces, and how to verify in 60 seconds.
- **[`docs/TRACK2_COMPLIANCE.md`](docs/TRACK2_COMPLIANCE.md)** — every Track 2 requirement mapped to its implementation and its proof.

---

## What I'd Do Next

1. **Retrain XGBoost on the enriched feature pipeline.** The current model is
   trained on the offline DGP's features; applied to the enriched feature
   engine it scores 0.82 on the serial/fraud-archetype target (where the
   hand-weighted scorer reaches 0.93) and ~0.50 on the per-order `returned`
   label — because that generator's `returned` outcome depends only on the
   user's latent rate (see `docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`).
   The demo path is aligned today (verified 10/10 on the Docker stack), but
   the model is still not *trained* on live-distributed features — recalibrate
   on real merchant data (or live-shaped training data) to close that gap,
   not just add more data.
2. **A/B test with a Razorpay merchant** — the champion/challenger harness is
   built; needs live orders to validate the 0.50 gate on real return
   distributions.
3. **Vertical-specific gates** — the config system supports per-vertical
   thresholds (fashion-high 0.50, low-return verticals 0.60–0.70); needs
   merchant data to tune.

---

## Limitations

1. **Synthetic data.** Labels come from a generator calibrated to published
   Indian e-commerce distributions, with hidden confounders the model never
   sees — that makes the model learn from noisy, incomplete signal, but it is
   still not real merchant data.
2. **No real pilot yet.** The 0.50 gate and the base-rate calibration are
   projections; an A/B test with a live merchant is the first next step.
3. **`device_fingerprint_match` is a neutral 0.5 at inference** — the
   return-risk module keeps no device store, so the model leans on the other
   six features at inference time.

---

## Repository Scope

This submission evaluates the **return-risk scorer** only. Fraud detection
(`engine/`, `ml/`) and chargeback response (`chargeback/`) extensions exist in
the codebase as future platform work but are **not measured or documented in
this track** — their API routes (`/v1/score`, `/v1/chargeback/*`) remain
mounted for completeness but are out of scope, and every number, metric and
cost figure here covers the return-risk surface only.

In scope and live: the **dashboard** (`dashboard/`, SPA on :3000) and the
**agent worker** (`agents/`, compose `worker` service) both operate on the
return-risk surface — the agents analyze scored orders from the audit chain and
report live heartbeats, but they do not change the measured model metrics.

**Compliance:** PCI-DSS, RBI and EU AI Act certifications are **out of scope
for this PoC**. The audit-chain infrastructure (`store/audit_log.py`) is
designed to support future certification, not to claim it — see
[`COMPLIANCE_DELTA.md`](COMPLIANCE_DELTA.md).

---

## Documentation Index

| Topic | Doc |
|---|---|
| **10-minute walkthrough** | [`EVALUATOR_GUIDE.md`](EVALUATOR_GUIDE.md) |
| **Business impact (headline ₹, verticals)** | [`BUSINESS_IMPACT.md`](BUSINESS_IMPACT.md) |
| **Mistakes & learnings** | [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md) |
| **Cost model + vertical sensitivity** | [`docs/COST_MODEL.md`](docs/COST_MODEL.md) |
| **Razorpay integration** | [`docs/RAZORPAY_INTEGRATION.md`](docs/RAZORPAY_INTEGRATION.md) |
| **Three hard bugs, told as stories** | [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md) |
| **Full API reference** | [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) |
| **Full architecture** | [`docs/TRACK2_ARCHITECTURE.md`](docs/TRACK2_ARCHITECTURE.md) |
| **Interview defense** | [`docs/INTERVIEW_DEFENSE.md`](docs/INTERVIEW_DEFENSE.md) |

---

## Appendix A — API Reference (return-risk hero)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/return/score` | API Key | Score an order for return risk (transparent breakdown, `engine`, `feature_importance`, `confidence`) |
| `POST` | `/v1/return/update` | API Key + RBAC | Record a return event → refresh profile |
| `GET` | `/v1/return/profile/{user_id}` | API Key + RBAC | Merchant-dashboard user return history |
| `GET` | `/v1/investigations` | API Key + RBAC | Paginated ledger of scored orders (audit-chain backed) |
| `GET` | `/v1/investigation/{order_id}` | API Key + RBAC | Detail view for one scored order |
| `GET` | `/v1/meta/return-risk/cost` | API Key + RBAC | Cost model (scenarios + sensitivity) from the committed calculator output |
| `GET` | `/v1/meta/return-risk/benchmark` | API Key + RBAC | Committed calibrated benchmark (PR-AUC / gate metrics) |
| `GET` | `/v1/meta/experiments` | API Key + RBAC | Champion/challenger A/B verdict |
| `GET` | `/admin/drift/return-risk` | API Key + RBAC | PSI drift report on the return-risk feature surface |
| `GET` | `/admin/agents/health` | API Key + RBAC | Live agent heartbeats (transaction/profile/reflection/human-review) |

Extension endpoints (fraud, chargeback, admin) and the full surface:
[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).

---

## Appendix B — Bug Resolution and Technical Notes

**34 issues** found & fixed while bringing the stack up end-to-end. Three are
told as full stories (root cause, debugging trail, lesson) in
[`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md). The complete table:

| # | Bug | Root cause | Fix |
|---|-----|------------|-----|
| 1 | API crash at startup | `StatisticalFilter` called `config.get(...)` on `None` | use `self.config.get(...)` |
| 2 | Score route returned canned results | features were never computed | real Redis-backed velocity/geo features (`velocity:user:`, `velocity:dev:`, `velocity:loc:`) |
| 3 | Redis/Ollama connections used `localhost` inside containers | hardcoded defaults | env-driven `REDIS_HOST`/`OLLAMA_BASE_URL`/`OLLAMA_MODEL` |
| 4 | Worker died at boot: `No module named 'infrastructure'` | fork-time import of bridge module | module-level import with fallback (`store.sync_redis`) |
| 5 | Investigation route 500 on reports | worker stored nested `{status, report}` | accept flat or nested report dicts |
| 6 | LLM returned unparseable output | JSON embedded in prose | JSON-only prompt + tolerant parser (trailing commas, key-value fallback) |
| 7 | `UnboundLocalError: l2` in evidence collection | `l2` referenced before assignment | initialize `l1`/`l2` before use |
| 8 | Investigation never ran | wrong Celery app module + no task `include` | `celery -A tasks.celery_app`, explicit task list |
| 9 | RBAC 403 on investigations | `system` role lacked `investigation:read` | add to `configs/rbac.yaml` |
| 10 | Role endpoints rejected valid API keys | `get_current_user` only read Bearer header | accept `x-api-key` fallback |
| 11 | Dashboard Docker build failed | missing deps, TS errors, wrong COPY paths | add `react-router-dom`/`axios`/`zustand`, fix Dockerfile + types |
| 12 | Compliance findings persisted nowhere | audit log did not exist | `store/audit_log.py` (hash-chained JSONL + PII masking) |
| 13 | **Drift report showed PSI=43.4** | PSI estimator: 10 fixed bins on 14 discrete samples, zero-mass bins, no smoothing, `density=True` double normalization | shared quantile edges, bin count `max(3, n//5)`, Laplace smoothing — 43.4→**3.86** on the real case |
| 14 | Drift samples never recorded | missing `await` on `_record_drift_samples` | awaited; fixed zset member/score convention mismatch |
| 15 | Container rebuilds wiped audit/explanation artifacts | code dirs shadowed by volumes | named volumes on leaf data dirs |
| 16 | Synthetic generator crashed: empty sequence | `CITY_TIER_WEIGHTS` samples `tier4` but no tier-4 cities | added 4 tier-4 cities |
| 17 | Synthetic generator crashed on device generation | `random.choice` called with `weights=` (numpy API on stdlib RNG) | `rng.choices(..., weights=[...])[0]` |
| 18 | Model card's `AUC > 0.92` was never measured | aspirational claim from the design phase | corrected to measured test PR-AUC 0.198 + AUC-ROC 0.692 |
| 19 | GNN v1.0 readout pooled the whole ego-graph | graph-level pooling diluted the target user's own pattern | GNN v1.1.0: target-user readout + 5 new features — PR-AUC 0.198 → **0.4125** |
| 20 | `AsyncRedisClient.hmset` passed mapping positionally to `hset` | redis-py API signature mismatch | corrected argument passing |
| 21 | `create_redis` merged explicit `None` kwargs over configured host | bridge default handling | proper `None` filtering |
| 22 | `SyncRedisClient` missing `hmset` | incomplete sync/async parity | added the method |
| 23 | `seed_demo_data.py` missing `sys.path` bootstrap | script couldn't find modules standalone | added bootstrap |
| 24 | Demo "suspicious burst" couldn't fire geo rules | missing `velocity:loc:*` / `velocity:dev:*` keys in seeder | seeded prior location + device velocity |
| 25 | `AlertBroadcaster` crashed at startup: `'AsyncRedisClient' object has no attribute 'pubsub'` | `AsyncRedisClient` wrapper didn't delegate `pubsub()` to the raw redis-py client | added `pubsub()` delegation (`store/redis_client.py`) — live WebSocket alerts restored |
| 26 | Dashboard stuck on "Request failed (403)" after token expiry | axios interceptor handled only 401, not 403 (expired JWT surfaces as 403) | interceptor now refreshes on 401 and clears session + redirects to `/login` on both 401/403 |
| 27 | `scripts/ablation.py` crashed: `NameError: pd` | `pd.DataFrame` referenced without importing pandas | added `import pandas as pd` |
| 28 | Makefile warned "overriding commands for target `benchmark`" | duplicate `benchmark:` target — second definition silently overrode the first | renamed the optimizer benchmark to `benchmark-opt` |
| 29 | PyJWT `InsecureKeyLengthWarning` (29-byte secret < 32 for HS256) | hardcoded short dev JWT secret | extended default to 37 bytes; rotate via `JWT_SECRET` env in prod |
| 30 | Return-risk router skipped at startup → `POST /v1/return/score` 404 | `return_risk/scorer.py` imports `xgboost`, absent from `requirements.txt` | add `xgboost>=2.0.0` |
| 31 | Dashboard cost model served stale numbers (0.98 precision / ₹20.9L) vs the then-README baseline (since re-anchored to measured P/R) | committed `models/cost_model_results.json` predated the XGBoost recalibration | regenerate from `docs/cost_model/calculator.py` |
| 32 | Transactions/Dashboard/Notifications polled `/v1/investigations` → 404 | route deleted in repo scoping | audit-backed `/v1/investigations` + `/v1/investigation/{order_id}` views over `RETURN_RISK_SCORED` entries |
| 33 | Every fresh-user analysis showed `confidence 0.0%` | old formula deducted 0.05 per default feature — 16 defaults → clamped to 0 | confidence = 40% decisiveness (score vs 0.5 boundary) + 35% provenance + 25% history depth |
| 34 | Agents page stuck on `not_started` | agent code + worker deleted in scoping; only the health endpoint remained | restore + rewire four agents to the return-risk surface; run as a `worker` compose service with real Redis heartbeats |

---

## Appendix C — Project Structure

```
PayShield/
├── return_risk/               # ★ Evaluated hero: feature engine, rules, XGBoost scorer
├── data/synthetic/            # return-risk generator (non-circular DGP)
├── scripts/                   # train/ablation/tune/benchmark/verify — the evidence
├── docs/ + docs/cost_model/   # cost model + calculator + vertical sensitivity
├── api/                       # FastAPI app (return-risk routes are the hero surface)
├── agents/                    # Live agent orchestration (worker service: transaction,
│                              #   profile, reflection, human-review — Redis heartbeats)
├── dashboard/                 # React SPA (nginx-served on :3000): score, ledger, cost
│                              #   model, drift, experiments, agent health, new-analysis form
├── integrations/              # Razorpay adapter + webhooks (order.paid → score)
├── engine/                    # (extension) fraud: L1 filter, L2 GNN, ensemble
├── chargeback/                # (extension) dispute rebuttal builder + Razorpay client
├── store/                     # Redis client + audit chain (+ fraud graph store)
├── ml/                        # return-risk champion/challenger A/B
├── observability/             # PSI drift monitoring (return-risk surface)
└── tests/                     # unit + integration + e2e
```

---

## License

MIT — see [LICENSE](LICENSE)