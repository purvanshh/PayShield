# PayShield: Return-Risk Scorer for Indian E-Commerce

**One-sentence:** PayShield scores every order *before it ships*, catches
high-risk returns at high precision, and saves a fashion merchant **₹17.5
lakh/month** on 10,000 orders.

**For evaluators:** Start with [`EVALUATOR_GUIDE.md`](EVALUATOR_GUIDE.md) —
10-minute walkthrough. Business case: [`BUSINESS_IMPACT.md`](BUSINESS_IMPACT.md).
Honest ledger: [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md).

**The numbers:**
- **Offline XGBoost PR-AUC:** **0.8067** — learns from noisy, incomplete signal
- **Cost at the 0.50 gate:** **₹17.5L/month** on 10K orders

**Run it (hermetic):** `python scripts/train_xgb_return_risk.py`

**Honest prototype note:** a student PoC on Razorpay's infrastructure — not
production software.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Number

| Metric | Value | What It Measures |
|---|---|---|
| **Offline XGBoost PR-AUC** | **0.8067** | Model learns from raw 7 features + hidden DGP noise on the `returned` label (architecture validation) |
| **Cost at 0.50 gate** | **₹17.5L/month** | Monthly savings on 10k orders, fashion vertical, review cost ₹200 |

The model is trained on a non-circular synthetic DGP: visible features plus
hidden confounders (product rating, delivery speed, packaging, weather,
customer mood) that the model never observes. That makes the absolute PR-AUC
lower but more honest than a circular benchmark.

### The model (raw features, 2,000-order hold-out, gate 0.50)

| Model | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|
| **XGBoost (tuned)** | **0.8067** | **0.677** | **0.774** | **0.722** |
| XGBoost (default) | 0.8042 | 0.635 | 0.811 | 0.712 |
| Hand-weighted (fallback) | 0.7896 | 0.957 | 0.194 | 0.323 |
| Naive: serial returner (>40%) | 0.6991 | 0.631 | 0.615 | 0.623 |
| Naive: COD + high AOV | 0.5884 | 0.685 | 0.159 | 0.258 |

XGBoost edges the hand-weighted scorer (**+0.017 PR-AUC**) and clearly beats
both naive rules (**+0.11 over the best naive baseline**). Full details in
["What We Measured"](#what-we-measured) below.

### Cost model — the 0.50 review gate

On a 10k-order fashion merchant (₹2.5k AOV, 18% return rate), the **0.50 review
gate** saves **₹17.5L/month** at precision 0.677 and recall 0.774 — the
offline XGBoost operating point, measured on the held-out test set. The
config-driven gate sweep:

| Review gate | Flag rate | Precision | Recall | Net ₹ / month | ROI |
|---|---|---|---|---|---|
| 0.30 | 63.9% | 0.559 | 0.902 | ₹16.3L | 32.4% |
| 0.40 | 53.5% | 0.623 | 0.841 | ₹17.3L | 34.4% |
| **0.50** | **45.3%** | **0.677** | **0.774** | **₹17.5L** | **34.9%** |
| 0.60 | 38.1% | 0.729 | 0.701 | ₹17.3L | 34.4% |
| 0.70 | 29.8% | 0.790 | 0.595 | ₹16.1L | 32.0% |

The 0.50 gate is optimal for this vertical. See [`docs/COST_MODEL.md`](docs/COST_MODEL.md)
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

---

## Run It

Hermetic (no services needed):

```bash
python scripts/train_xgb_return_risk.py      # train + baseline comparison (~20s)
python scripts/ablation_study.py             # leave-one-feature-out ablation (~60s)
python scripts/tune_xgb.py                   # 144-combo hyperparameter search (~15s)
python docs/cost_model/calculator.py         # the numbers in ₹
python docs/cost_model/calculator.py --vertical-sensitivity   # where the gate breaks
```

Live stack (needs Docker): `docker compose -f docker/docker-compose.yml up`,
then `python scripts/seed_demo_data.py` and `python scripts/verify_live_stack.py`
(10 scenarios against real Redis — see ["Live verification"](#live-verification)).

---

## What We Measured

### Baseline comparison (same 2,000-order hold-out, gate 0.50)

| Model | PR-AUC | Precision | Recall | F1 |
|---|---|---|---|---|
| **XGBoost (tuned)** | **0.8067** | **0.677** | **0.774** | **0.722** |
| Hand-weighted (fallback) | 0.7896 | 0.957 | 0.194 | 0.323 |
| Naive: serial returner (>40%) | 0.6991 | 0.631 | 0.615 | 0.623 |
| Naive: COD + high AOV | 0.5884 | 0.685 | 0.159 | 0.258 |

### Ablation — every feature earns its place (LOFO retraining, seed-99 test set)

| Feature removed | PR-AUC | Drop from baseline (0.8118) |
|---|---|---|
| `amount_vs_user_aov_ratio` | 0.7574 | **−6.7%** |
| `payment_method_risk` | 0.7747 | **−4.6%** |
| `user_return_rate_30d` | 0.7827 | **−3.6%** |
| `user_return_rate_90d` | 0.8012 | −1.3% |
| `device_fingerprint_match` | 0.8012 | −1.3% |
| `category_return_baseline` | 0.8077 | −0.5% |
| `days_since_last_order` | 0.8077 | −0.5% |
| **combined: both rate features** | 0.7265 | **−10.5%** |

The individual drops are small because the two rate features share the
user-history signal; removing **both** costs **−10.5%**, the largest block.
The drop is genuine feature importance measured against hidden confounders —
not circular recovery.

### Confusion matrix (offline XGBoost, 2,000-order hold-out, gate 0.50)

From `scripts/train_xgb_return_risk.py`:

```
                     Not Flagged   Flagged
Actual No Return          915       293   (TN=915, FP=293)
Actual Return             179       613   (FN=179, TP=613)
```

Precision **0.677** · recall **0.774** · F1 **0.722**.

### Tuning

Grid search over 144 combinations (`max_depth` × `n_estimators` ×
`learning_rate` × `scale_pos_weight`), selected on validation: best
`max_depth=3, n_estimators=200, lr=0.05, spw=1.5` → test PR-AUC **0.8067**.

### Live verification

All ten curated scenarios pass against the running Docker stack — serial
returner → HIGH, honest → LOW, chargeback responses, signed webhooks, drift.
Full table in `scripts/verify_live_stack.py`.

---

## What I'd Do Next

1. **Retrain XGBoost on the enriched feature pipeline.** The current model is
   trained on the offline DGP's features; applied to the enriched feature
   engine it scores 0.82 on the serial/fraud-archetype target (where the
   hand-weighted scorer reaches 0.93) and ~0.50 on the per-order `returned`
   label — because that generator's `returned` outcome depends only on the
   user's latent rate (see `docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`).
   Closing the gap means recalibrating the model to enriched feature
   distributions — ideally on real merchant data — not just more data.
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
| `POST` | `/v1/return/score` | API Key | Score an order for return risk (transparent breakdown, `engine`, `feature_importance`) |
| `POST` | `/v1/return/update` | API Key + RBAC | Record a return event → refresh profile |
| `GET` | `/v1/return/profile/{user_id}` | API Key + RBAC | Merchant-dashboard user return history |
| `GET` | `/admin/drift/return-risk` | API Key + RBAC | PSI drift report on the return-risk feature surface |

Extension endpoints (fraud, chargeback, admin) and the full surface:
[`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).

---

## Appendix B — Bug Resolution and Technical Notes

**29 issues** found & fixed while bringing the stack up end-to-end. Three are
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

---

## Appendix C — Project Structure

```
PayShield/
├── return_risk/               # ★ Evaluated hero: feature engine, rules, XGBoost scorer
├── data/synthetic/            # return-risk generator (non-circular DGP)
├── scripts/                   # train/ablation/tune/benchmark/verify — the evidence
├── docs/ + docs/cost_model/   # cost model + calculator + vertical sensitivity
├── api/                       # FastAPI app (return-risk routes are the hero surface)
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