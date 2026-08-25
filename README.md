# PayShield: A Student-Built Prototype for Honest Return-Risk Scoring

**PayShield is a Proof-of-Concept return-risk scoring system for Indian e-commerce merchants, built on Razorpay's infrastructure** (a student prototype — not production software). It scores every order *before it ships*, catches the high-risk tail at 98% precision, and saves a fashion merchant ~₹21 lakh/month by preventing returns instead of absorbing them. Fraud detection and chargeback response ship as platform extensions on the same audit chain.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Numbers (30 seconds)

**Primary finding — the cost-model operating-point sweep.** On a
high-return population (base rate ~32%+, Amazon-style margins) the default
**0.30 review gate floods**: it flags ~3 of every 4 orders, precision
collapses, and the merchant **loses** ~₹9.8 cr/month. Raising the config-driven
gate to **0.50** keeps precision ~0.63 at an 18% flag rate and flips the
economics **positive** — the single highest-leverage fix in the project:

| Review gate | Flag rate | Precision | Net ₹ / month | ROI |
|---|---|---|---|---|
| **0.30 (before)** | 75.3% | 0.464 | **−₹9.8 cr** | **−38.9%** |
| 0.45 | 19.9% | 0.612 | +₹0.46 cr | +1.8% |
| **0.50 (after)** | 18.3% | 0.633 | **+₹0.81 cr** | **+3.2%** |

Sweep measured on the reconstructed Amazon 2025 population — full story and
methodology in [`docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`](docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md).
Compounding it, the [Review-vs-Block cost fix](docs/COST_MODEL.md) charges a
wrong MEDIUM flag ₹200 (operator time, the order still ships) instead of the
full ₹3,180 — making the surplus strictly larger.

The shipped operating points are measured on a **10,000-order benchmark
generated with priors calibrated against public Indian e-commerce
distributions (Amazon India 2025 category margins)** — 500 users × 5
archetypes, seed 42, chronological per-user hold-out, so no score ever uses
future returns:

| Metric | Value | Meaning |
|---|---|---|
| **PR-AUC** | **0.9311** | Rank quality on the minority (return) class |
| **Precision @ MEDIUM+** | **0.9837** | ~1 in 60 flagged orders is a wrong review flag |
| **Recall @ MEDIUM+** | **0.6050** | Catches the clearly-high tail (review gate 0.50, tuned per vertical) |
| **F1 @ MEDIUM+** | **0.7492** | Primary operating point |
| Precision @ HIGH gate | 0.9837 | Prepaid gate |
| Recall @ HIGH gate | 0.6050 | |
| ROC-AUC | 0.9431 | |

The review gate (MEDIUM+) is config-driven (`configs/return_risk_rules.yaml`
→ `operating_point.medium_review_threshold`): **0.50 for high-return-rate
vertical (base rate ~32%+), 0.30–0.35 for low-return fashion (~14–18%)**.

Every precision/recall point is translated into **merchant money** — see [`docs/COST_MODEL.md`](docs/COST_MODEL.md): a wrong MEDIUM flag costs ₹200 of operator time (review), a wrong HIGH block costs ₹3,180. At the review gate a 10k-order fashion merchant **prevents ~750 returns/month**, cuts return cost by **41.6%** (₹50.31L → ₹29.38L), and nets **~₹2,09,000 saved per 1,000 orders**.

Run it yourself — hermetic, no services needed:

```bash
python scripts/benchmark_return_risk.py      # precision/recall/F1/PR-AUC/ROC-AUC
python docs/cost_model/calculator.py          # the same metrics in ₹
```

---

## The Architecture (30 seconds)

```
[Razorpay order.paid]  ──►  POST /v1/return/score
                                 │
                 ┌───────────────┼──────────────────┐
                 ▼               ▼                  ▼
        ┌────────────────┐ ┌──────────────┐ ┌───────────────┐
        │ Feature Engine  │ │ Rules Engine │ │  Redis Store  │
        │ 7 weighted      │ │ 8 config-    │ │ user history, │
        │ features from   │ │ driven rules │ │ merchant      │
        │ user+merchant+  │ │ (YAML,       │ │ baselines,    │
        │ txn context     │ │ hot-reload)  │ │ return zsets  │
        └────────┬────────┘ └──────┬───────┘ └───────────────┘
                 └────────┬────────┘
                          ▼
              ┌──────────────────────┐
              │  Weighted composite  │   transparent: every feature's
              │  score + rule boost  │   value, weight & contribution
              └──────────┬───────────┘
                         ▼
              ┌──────────────────────┐
              │  Tier: LOW / MEDIUM  │   LOW → ACCEPT (ship)
              │        / HIGH        │   MEDIUM → FLAG_FOR_REVIEW
              └──────────────────────┘   HIGH → REQUIRE_PREPAID
```

The score is **fully transparent**: every feature carries a value, a normalised value, a weight and a contribution, plus a `source` tag (`redis_hash`, `computed`, `lookup_table`, `default_new_user`) — so a 0.83 can be explained down to the penny, and degraded data is visible, never hidden. Weights come from `configs/feature_registry_return.yaml`, tiers/rules from `configs/return_risk_rules.yaml` (reloadable without a deploy).

The subtle design point: a **wrong MEDIUM flag costs ₹200 of operator time** (the order still ships), while a **wrong HIGH/prepaid block costs ₹3,180** (lost order + CAC + churn). Because review is cheap and blocking is expensive, the gate is tuned to favour *precision at the review tier* — the threshold selection is a cost optimisation, not an accuracy aspiration, and the review gate is config-driven per merchant vertical.

---

## Live Verification (30 seconds)

All scenarios tested against the **running Docker stack** (real Redis/Postgres, not in-memory fakes) — `python scripts/verify_live_stack.py`:

| Scenario | Endpoint | Expected | Measured |
|---|---|---|---|
| Serial returner | `POST /v1/return/score` | HIGH ~0.83 | **HIGH · 0.8551** |
| Honest customer | `POST /v1/return/score` | LOW ~0.10 | **LOW · 0.1628**¹ |
| Winnable chargeback | `POST /v1/chargeback/respond` | REJECT | **REJECT · conf 1.0** |
| Weak chargeback | `POST /v1/chargeback/respond` | PARTIAL + warnings | **PARTIAL · 0.68 + 2 warnings** |
| Clean transaction | `POST /v1/score` | ALLOW ~0.08 | **ALLOW · 0.0624** |
| Suspicious burst | `POST /v1/score` | BLOCK | **BLOCK · 1.0** `[V-RULE-03, G-RULE-01, G-RULE-02]` |
| Webhook bad signature | `POST /webhooks/razorpay/chargeback` | 400 | **400** |
| Webhook valid signature | `POST /webhooks/razorpay/chargeback` | 200 | **200** |
| Return callback | `POST /v1/return/update` | SUCCESS | **SUCCESS** |
| Drift report | `GET /admin/drift/return-risk` | 200 | **200** |

¹ 0.1628 measured on a fresh seed; live profiles drift ~0.10–0.22 after background-refresh increments — still LOW tier.

The weak-chargeback row is the graceful-degradation behaviour: incomplete evidence produces `PARTIAL` with explicit warnings, never a crash or an overconfident `REJECT`. Dedicated failure-mode demo: `python scripts/demo_graceful_failure.py`.

---

## What I'd Do Next

1. **A/B test with a real merchant** — the champion/challenger harness is built (`scripts/simulate_ab_test.py` + `ml/ab_testing.py`); it needs live orders to hurt.
2. **Seasonal features** — festive return spikes (Diwali/New Year) are a documented blind spot; `txn_is_salary_day` is the only calendar feature today.
3. **GPU inference** for the graph extension layer (CPU p99 0.70 ms today, already non-blocking).
4. **Continuous feedback** — analyst overrides are ingested (`human_review_agent`) but not yet on the live decision path.

---

## Quick Start

```bash
# 1. Start everything
docker compose -f docker/docker-compose.yml up

# 2. Seed the six curated demo scenarios (verified outputs in docs/DEMO_DATA.md)
python scripts/seed_demo_data.py

# 3. Live-stack verification (10 scenarios against real services)
python scripts/verify_live_stack.py

# 4. Benchmarks (hermetic — no services needed)
python scripts/benchmark_return_risk.py
python docs/cost_model/calculator.py
python scripts/simulate_ab_test.py
python scripts/demo_graceful_failure.py

# 5. Score an order
curl -X POST http://localhost:8000/v1/return/score \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD_DEMO_001",
    "user_id": "U_SERIAL_001",
    "merchant_id": "M_FASHION_001",
    "amount": 5500,
    "category": "fashion",
    "payment_method": "UPI",
    "cod_flag": true
  }'

# 6. End-to-end flow tests
python -m pytest tests/integration/test_chargeback_flow.py -v

# 7. Open the operator UI — login admin / admin by default
open http://localhost:3000
```

> **Important:** rebuild the API image after code changes — `docker compose build api` before `docker compose up`.

**Demo script:** [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) · **Verified data:** [`docs/DEMO_DATA.md`](docs/DEMO_DATA.md) · **Judge Q&A:** [`docs/JUDGE_QA.md`](docs/JUDGE_QA.md) · **Architecture:** [`docs/TRACK2_ARCHITECTURE.md`](docs/TRACK2_ARCHITECTURE.md)

---

## Operator UI

The frontend is a **Vite + React + TypeScript** SPA styled with Tailwind
(Material-3 dark palette: warm gold `#e5c484` on near-black `#16130f`, grain
overlay, Geist + Instrument Serif type), served by nginx at
**http://localhost:3000** — SPA routing configured, so deep links work.

**Sign-in**
- Unauthenticated visitors are redirected straight to the login screen.
- Username/password **`admin` / `admin`** by default (`ADMIN_USERNAME` /
  `ADMIN_PASSWORD` env — `api/routes/auth.py`). After sign-in the login screen
  never reappears; **Sign Out** lives in the sidebar.

**Top navigation (primary workflows)** — Fraud · Return Risk · Chargeback.

**Sidebar (risk operations)** — complements the top nav instead of duplicating it:

| Surface | Route | What it shows |
|---|---|---|
| Cost Model | `/cost-model` | The ₹20,92,650/month savings story, computed live from the `docs/cost_model` assumptions (scenario + sensitivity tables) |
| Drift Monitor | `/drift` | Live PSI across the return-risk feature surface (`GET /admin/drift/return-risk`) |
| A/B Experiments | `/experiments` | Champion/challenger verdict with Welch p-value — models promote only on significance |
| Agents | `/agents` | Health of the four live orchestration agents (`GET /admin/agents/health`) |
| Support | `/support` | FAQ, contact channels, system snapshot |
| Transactions | `/transactions` | Full risk ledger — the "View All" destination from the fraud dashboard |

**Functional surfaces**
- **Notifications** (bell) → live panel of recent anomalies with unread badge,
  mark-all-read, and "view all activity".
- **New Analysis** (sidebar) → modal that starts a workflow: fraud transaction,
  return-risk order, or chargeback dispute.
- **Legal** → Privacy / Terms / Security Disclosure / Regulatory pages
  (placeholder content) from the footer.

**Development:** `cd dashboard && npm install && npm run dev` →
http://localhost:5173 (`VITE_API_URL` defaults to `http://localhost:8000`).

---

## Platform Extensions

PayShield covers the full lifecycle of merchant loss — proactive return-risk scoring is the hero, and **reactive fraud detection** and **remedial chargeback response** extend the same tamper-evident audit chain:

```
[Order]        →  /v1/return/score       → "will this come back?"      (proactive hero)
[Transaction]  →  /v1/score              → "is this fraud right now?"  (reactive extension)
[Dispute]      →  /v1/chargeback/respond → "can we win this contest?"  (remedial extension)
```

### 1. Fraud Detection extension — `POST /v1/score`

A 3-layer fraud system underpinning the risk platform:

| Layer | Component | Measured |
|---|---|---|
| **L1** | Statistical filter — velocity / geo / Benford (12 config-driven rules) | p99 0.27 ms pure rule eval; hot path p50 8.5 ms / p99 63.3 ms |
| **L2** | Heterogeneous GNN (PyTorch Geometric, HeteroConv + GraphSAGE, target-user readout) | Test PR-AUC 0.4125 — **4.0× vs edge-free MLP** (0.1028); inference p99 0.70 ms. Deliberately **conditional fusion**: runs for returning users, skips fresh users (`SKIPPED_NO_GRAPH`), 40 ms timeout guard with L1 fallback |
| **L3** | LLM investigation (Ollama `qwen2.5:3b`) | Async via Celery (~35 s), never blocks the hot path, validated JSON reports with quality scores |

Full honest GNN numbers (v1.0.0 → v1.1.0, the `AUC > 0.92` correction) live in the [model card](models/payshield_gnn_v1_card.md) and `models/gnn_benchmark_results.json`.

### 2. Chargeback Response extension — `POST /v1/chargeback/respond`

Rebuilds a dispute rebuttal from evidence captured at transaction time (L1 rule snapshots, L2 GNN score, L3 investigation), overlays merchant delivery proof, generates the narrative with the LLM stack and hands the merchant a ready-to-submit **Razorpay dispute payload**. Submission is never automatic — `chargeback:admin` only.

- Network-aware deadlines (UPI 7d / Visa·MC 30d / Amex 20d / RuPay 15d)
- Honest completeness + confidence; weak cases degrade to conservative `PARTIAL` with warnings
- Signed webhook (`/webhooks/razorpay/chargeback`) with HMAC verification, auto-rebuttal caching, mock-mode Razorpay client with realistic fixtures

### Ticket / Razorpay integration surface

The return-risk scorer is designed to sit **inside a Razorpay merchant flow** as a pre-shipping risk layer:
`order.paid` webhook → score → merchant WMS acts on the recommendation. The adapter, webhook handler, fixtures and field-mapping tables live in [`integrations/`](integrations/) — see [`docs/RAZORPAY_INTEGRATION.md`](docs/RAZORPAY_INTEGRATION.md).

---

## Documentation Index

| Topic | Doc |
|---|---|
| **Cost model (false positives vs false allows, in ₹)** | [`docs/COST_MODEL.md`](docs/COST_MODEL.md) |
| **Razorpay integration (adapter + webhooks)** | [`docs/RAZORPAY_INTEGRATION.md`](docs/RAZORPAY_INTEGRATION.md) |
| **Three hard bugs, told as stories** | [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md) |
| **Graceful failure design** | [`docs/GRACEFUL_FAILURE.md`](docs/GRACEFUL_FAILURE.md) |
| **A/B experiment simulation** | [`scripts/simulate_ab_test.py`](scripts/simulate_ab_test.py) |
| **Return-risk feature/rule reference** | [`docs/reference/return_risk_redis_schema.md`](docs/reference/return_risk_redis_schema.md) · [`docs/reference/return_risk_patterns.md`](docs/reference/return_risk_patterns.md) |
| **Full architecture** | [`docs/TRACK2_ARCHITECTURE.md`](docs/TRACK2_ARCHITECTURE.md) |
| **Return-risk model card** | [`models/return_risk_benchmark_results.json`](models/return_risk_benchmark_results.json) |

---

## Appendix A — API Reference

### Return-Risk (hero)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/return/score` | API Key | Score an order for return risk (transparent breakdown) |
| `POST` | `/v1/return/update` | API Key + RBAC | Record a return event → refresh profile |
| `GET` | `/v1/return/profile/{user_id}` | API Key + RBAC | Merchant-dashboard user return history |
| `GET` | `/admin/drift/return-risk` | API Key + RBAC | PSI drift report on the return-risk feature surface |

### Fraud Detection (extension)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/score` | API Key | Score a single transaction |
| `POST` | `/v1/batch` | API Key + RBAC | Score up to 100 transactions |
| `GET` | `/v1/investigation/{txn_id}` | API Key | LLM investigation report |
| `GET` | `/v1/investigations` | API Key + RBAC | List investigations (paginated) |

### Chargeback (extension)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/v1/chargeback/respond` | API Key + RBAC | Build a dispute rebuttal + Razorpay payload |
| `POST` | `/webhooks/razorpay/chargeback` | HMAC | Razorpay chargeback webhook (signed) |
| `POST` | `/v1/feedback` | API Key + RBAC | Submit analyst decision |

### Admin & Ops
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/admin/rules/reload` | API Key + RBAC | Reload statistical rules from YAML |
| `POST` | `/admin/models/promote` | API Key + RBAC | Promote model version |
| `POST` | `/admin/config/threshold` | API Key + RBAC | Update scoring threshold |
| `GET` | `/admin/agents/health` | API Key + RBAC | Agent health status |
| `GET` | `/admin/drift/psi` | API Key + RBAC | PSI drift report (yesterday vs today) |
| `POST/GET` | `/admin/experiments` | API Key | Champion/challenger experiments |
| `GET` | `/health` / `/metrics` | None | Health + Prometheus metrics |

Full reference: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

---

## Appendix B — Measured Findings (Fraud Extension)

Everything below is measured against the live stack, not simulated.

| Scenario | Result |
|----------|--------|
| Normal single transaction (₹4.5k, new user) | ALLOW — ~1-3 ms |
| Velocity burst (12+ rapid transactions, ₹95k each) | BLOCK / REVIEW — `V-RULE-02` / `V-RULE-03` |
| Geo jump (Mumbai → Delhi in 20 min) | BLOCK — `G-RULE-01`, `G-RULE-02` |
| LLM investigation (qwen2.5:3b, async) | Valid JSON report — `MERCHANT_COLLUSION`, quality 1.0, served from `investigation:{txn_id}` |

### Drift detection (PSI, rolling 24h windows)

```
  txn_count_5m               PSI=0.0123  STABLE
  txn_count_1h               PSI=0.0123  STABLE
  amount_total_1h            PSI=3.8608  DRIFT   ← hourly amount aggregate shifted ~33%
  device_txn_count_24h       PSI=0.0089  STABLE
  distinct_users_last_24h    PSI=0.0000  STABLE
  distinct_merchants_1h      PSI=0.0000  STABLE
```

The estimator itself was fixed during development (PSI=43.4 → 3.86 on a real shift) — see the first story in [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md).

---

## Appendix C — Bug Resolution and Technical Notes

**29 issues** found & fixed while bringing the stack up end-to-end. Three of them are told as full stories (root cause, debugging trail, lesson) in [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md). The complete table:

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

---

## Appendix D — Project Structure

```
PayShield/
├── api/                       # FastAPI app (15 route files)
│   ├── routes/                # health, score, return_risk, chargeback, chargeback_webhook, ...
│   ├── main.py                # App factory + middleware wiring
│   ├── schemas/               # Pydantic request/response models
│   └── lifespan.py            # Startup/shutdown resource lifecycle
│
├── return_risk/               # ★ Return-risk hero module
│   ├── feature_engine.py      # 7 weighted features + Redis feature store adapters
│   ├── rules_engine.py        # 8 config-driven rules (YAML, reloadable)
│   ├── scorer.py              # Transparent composite score → tier → recommendations
│   └── recommendations.py     # Actionable, tier-scoped recommendations
│
├── integrations/              # ★ Razorpay platform adapter
│   ├── razorpay_adapter.py    # order/refund payloads → PayShield feature schema
│   ├── razorpay_webhook_handler.py # order.paid → score; refund.processed → label
│   └── fixtures/              # sample Razorpay order/refund/dispute payloads
│
├── docs/                      # cost model, razorpay integration, hard bugs, graceful failure, ...
│   └── cost_model/            # calculator.py + assumptions.py + scenarios.json
│
├── chargeback/                # Dispute rebuttal builder + Razorpay client (mock/real)
├── engine/                    # L1 statistical filter, L2 GNN, ensemble fusion
├── agents/                    # 4-agent orchestration (see docs/TRACK2_ARCHITECTURE.md)
├── llm/                       # Ollama investigation stack
├── compliance/                # regulatory scorecard checkers (see Appendix F)
├── store/                     # Redis / Postgres / Neo4j / audit chain
├── data/synthetic/            # return-risk + UPI transaction generators
├── observability/             # PSI drift monitoring, Prometheus metrics
├── ml/                        # model lifecycle, champion/challenger A/B
├── dashboard/                 # Operator UI — Vite + React + TS + Tailwind (see Operator UI)
├── scripts/                   # benchmarks, demos, verification, seeding
├── tests/                     # unit + integration + e2e + load
└── Makefile                   # 30+ targets (test, lint, train, retrain, deploy)
```

## Appendix E — Agent System

Return-risk is minimal by design. Full rationale in [`docs/TRACK2_ARCHITECTURE.md`](docs/TRACK2_ARCHITECTURE.md) — development-only agents are archived under `agents/archived/` for transparency.

| Live agent | Responsibility |
|---|---|
| `transaction_agent` | Extracts order features + evaluates rules |
| `profile_agent` | Maintains user return/order history |
| `reflection_agent` | Nightly false-positive clustering + weight sync |
| `human_review_agent` | Ingests analyst overrides |

---

## Appendix F — Ops, ML Lifecycle, Compliance & Deployment

### Model training & promotion

```bash
make generate-data      # synthetic training data
make train              # train the GNN
make evaluate           # evaluate on validation set
make retrain            # benchmark candidate, gate (ε 0.005 PR-AUC), promote on improvement
```

### Operations

```bash
make up / down / build / logs      # Docker compose lifecycle
make chaos-run / chaos-test        # chaos experiments
make compliance-check / -report    # programmatic compliance
python scripts/run_drift_report.py # PSI drift (or GET /admin/drift/psi)
```

### CI / CD

| Stage | Tool |
|-------|------|
| Lint / format | `ruff check .` / `ruff format .` |
| Type check | `mypy api/ engine/ agents/` |
| Tests (coverage ≥ 70%) | `pytest --cov --cov-report=term-missing` |
| Security | `bandit -r .` |
| Deploy | ArgoCD → Kubernetes (`k8s/overlays/prod`) — projected, not wired to CI |

### Compliance & deployment scorecards (Proof-of-Concept — hidden, aspirational)

<details>
<summary><b>Compliance checkers & k8s deployment — not external audits, not shipped</b></summary>

These numbers come from the prototype's *programmatic* checkers
(`python scripts/security_audit_check.py` / `make compliance-check`). They
are self-assessments, not third-party audits, and the Kubernetes deployment is
a projected state with no CI workflow behind it.

| Framework | Before | After | Status |
|-----------|--------|-------|--------|
| PCI-DSS | 60/100 | **90/100** | checker result (no high-severity findings) |
| RBI | 16/100 | **83/100** | checker result |
| EU AI Act | — | **100/100** | checker result |

Deployment path (projected): Docker Compose for local/demo → ArgoCD →
Kubernetes (`k8s/overlays/prod`) with sealed secrets and an ingress manifest.
As a Proof-of-Concept this path is documented, not operated.
</details>

### Environment variables

See `.env.example`. Key ones: `PAYSHIELD_DEV_API_KEY` (API auth), `REDIS_HOST`/`REDIS_PORT`, `DATABASE_URL`, `NEO4J_URI`, `OLLAMA_BASE_URL`, `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` (test-mode Razorpay integration), `RAZORPAY_WEBHOOK_SECRET`.

---

## License

MIT — see [LICENSE](LICENSE)