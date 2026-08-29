# PayShield — Track 2 Execution Report

**Date:** 2026-08-29 · **Status:** Phases 0–6 all ✅ complete ·
**Branch:** `master`

This report is the living status of the Track 2 execution plan. It records
what is achieved, the evidence, and exactly what remains — so the next working
session can pick up without re-deriving context.

---

## 1. Headline status

| Area | Status | Evidence |
|---|---|---|
| Hermetic ML verification | **11/11 PASS** | `python scripts/run_all_scenarios.py --full-verify` → `ALL CHECKS PASS` (now incl. temporal-integrity check) |
| Live Docker stack | **11/11 PASS** | `seed_demo_data.py` + `verify_live_stack.py` |
| Test suite | **495 passed, 1 skipped** | `pytest tests/` (47 modules) |
| Track 2 compliance map | **20/20 verified** | `GET /v1/meta/track2-compliance` + `docs/TRACK2_COMPLIANCE.md` |
| Business case | **₹17.4L → ₹53.5L/month** | `docs/cost_model/calculator.py --all-maturity` |
| Explainability | **XGBoost waterfall live** | `POST /v1/return/explain` + dashboard Model Waterfall |
| Abuse-ring sentinel | **live + seeded demo ring** | score `U_RING_00x` w/ pincode `560037` → ring caught at HIGH 0.85 |
| Review queue | **live (audit-chain backed)** | `GET/POST /v1/meta/review-queue` + dashboard `/review-queue` |
| Simulator | **live (basic vs premium)** | `POST /v1/return/simulate` + dashboard `/simulator` |
| Guided demo | **live 10-minute tour** | `GET /v1/meta/demo/guide` + dashboard `/demo-tour` |

> **Integrity note:** the original plan's premise ("live stack 8/10 — honest
> customer → MEDIUM, suspicious burst → ALLOW") is **no longer true**. Both
> failures were fixed (commit `4207ff6`) by aligning the live feature pipeline
> to the model's training envelope — not by hardcoding demo overrides. The
> honest ledger is in [`docs/CALIBRATION_GAP.md`](../docs/CALIBRATION_GAP.md).
> Consequently, the plan's `--demo-mode` flag (which skipped the failing tests)
> was **not** implemented: skipping passing tests would be worse than pointless.

---

## 2. Completed work, by commit

### Baseline (previous sessions) — reproducibility + live fix

| Commit | What | Why it matters |
|---|---|---|
| `821d27f` | Pinned py311 ML stack (numpy 2.2.6, pandas 3.0.3, scipy 1.17.1, sklearn 1.9.0, xgboost 3.2.0); re-anchored every number + manifest to it; auto-heal macOS OpenMP in `--full-verify` | A judge cloning the repo now reproduces **byte-identical** numbers on macOS *and* Linux; xgboost no longer crashes on a missing OpenMP runtime |
| `4207ff6` | Fixed `amount_vs_user_aov_ratio` (AOV no longer falls back to `avg_return_value`); realistic demo profiles; regression tests pin honest→LOW and serial→HIGH | Live stack went from 8/10 → **11/11** |

### Phase 0 — Foundation & documentation overhaul ✅

| Commit | What |
|---|---|
| `7c21d10` `docs(judges): restructure cheat sheet and add honest calibration-gap accounting` | Rewrote [`JUDGES_CHEAT_SHEET.md`](../JUDGES_CHEAT_SHEET.md) to a 30-second / 5-minute / 10-minute structure with current verified numbers; added [`docs/CALIBRATION_GAP.md`](../docs/CALIBRATION_GAP.md) as the honest ledger of the two historical live failures, their fixes, and the **remaining** genuine gap (model still not trained on live-distributed features); linked it from the README live-verification section |

**Phase 0 checklist:**
- [x] JUDGES_CHEAT_SHEET.md — present, accurate, judge-first
- [x] README live-verification statement — accurate (11/11, not the stale 8/10)
- [x] docs/CALIBRATION_GAP.md — honest history + remaining gap
- [x] Commit per phase with conventional message — done (`docs(judges)`)
- [ ] `--demo-mode` flag — **deliberately skipped** (see integrity note above)

### Phase 1 — Track 2 Compliance dashboard ✅

| Commit | What |
|---|---|
| `1de357e` `feat(api): add Track 2 compliance metadata endpoint` | `GET /v1/meta/track2-compliance` serves the requirement → implementation → evidence map (20 items: 14 verified `done`, 6 `planned`), mirroring [`docs/TRACK2_COMPLIANCE.md`](../docs/TRACK2_COMPLIANCE.md) so docs and API can't drift. Integration tests assert auth + shape + honest status flags |
| `f0b6fd0` `feat(dashboard): add Track 2 Compliance page` | `/track2-compliance` route renders the map with DONE/PLANNED pills, a verified-count badge (14/20), and the overall summary; linked in the sidebar Operations section. TypeScript + Vite production build passes |

**Phase 1 verification:**
- `curl /v1/meta/track2-compliance` on the Docker stack → 20 requirements, 14 done / 6 planned, `403` without API key ✅
- Dashboard `npm run build` (tsc + vite) ✅

### Phase 2 — Feature-Waterfall Explainability ✅

| Commit | What |
|---|---|
| `e3b9803` `feat(api): add feature-waterfall explain endpoint` | `POST /v1/return/explain` scores an order (same inputs as `/score`) and returns the XGBoost feature waterfall: per-feature gain importance × normalized value (capped at the model's training envelope), the model score, tier, and neutral `base_score=0.5`, with an honest note that the attribution is approximate (nonlinear model). Read-only — never mutates Redis. Tests: auth, shape/order, read-only guarantee |
| `98c92a1` `feat(dashboard): render XGBoost feature-waterfall on the return-risk page` | Return Risk page calls `/v1/return/explain` per preset and shows a collapsible **Model Waterfall** (per-feature value / importance / contribution bars + the approximation note). TS/Vite build passes |

### Phase 3 — Abuse-Ring Sentinel & Temporal Integrity ✅

| Commit | What |
|---|---|
| `8372fca` `feat(return-risk): add abuse-ring sentinel (shared address + velocity)` | `txn_shared_address_count` via per-address SHA-256 set (no PII in keys); `R-RULE-09` `OVERRIDE_SCORE` raises the score floor to 0.85 (defense-only REQUIRE_PREPAID, never rewrites the model/weights); score/explain routes pass `shipping_address` (pincode-first); seeded 4-user demo ring on `560037`. Tests: ring → HIGH, family co-shipping → no false positive, PII-free key, seeded ring |
| `2bd59d4` `feat(verify): add temporal-integrity check to the verification suite` | `scripts/verify_temporal_integrity.py` proves no look-ahead on the seeded DGP (seed 99): per-user chronology, split `max(train) ≤ min(val) ≤ min(test)`, first-order features latent-sampled. Wired as `--full-verify` check 11 (suite now 11 checks) |
| `c49614e` `fix(verify): adjacent-pair zip in temporal-integrity check` | `zip(strict=True)` requires equal lengths — the adjacent-pair check pairs N vs N−1 timestamps, so strict mode always raised. Plain loop; 11/11 confirmed on the canonical py311 stack |

**Phase 3 verification (live, Docker stack):**
- Ring users `U_RING_001..003` → **LOW 0.1157** (model blind to the pattern), `U_RING_004` on the shared pincode → **HIGH 0.85** with `R-RULE-09` ✅
- `POST /v1/return/explain` (serial) → score 0.9441 HIGH, 7-item waterfall, top driver `payment_method_risk` ✅
- `--full-verify` → **11/11 PASS** ✅
- `verify_live_stack.py` → **11/11 PASS** (unchanged; curated scenarios don't send a shipping address, so the sentinel stays orthogonal) ✅

---

## 3. Verification (run before any further commit)

```bash
# Hermetic (Python 3.11 + pinned requirements)
python scripts/run_all_scenarios.py --full-verify     # 11/11 PASS

# Live Docker stack
docker compose -f docker/docker-compose.yml up -d --build api redis
python scripts/seed_demo_data.py
python scripts/verify_live_stack.py                   # 11/11 PASS

# Tests
pytest tests/                                         # 495 passed, 1 skipped

# Compliance endpoint (20/20 verified)
curl -s -X GET http://localhost:8000/v1/meta/track2-compliance \
  -H "X-API-Key: payshield-dev-key-2026" | jq '.requirements | length'   # 20 (all done)

# Review queue + mark
curl -s http://localhost:8000/v1/meta/review-queue -H "X-API-Key: payshield-dev-key-2026"
curl -s -X POST http://localhost:8000/v1/meta/review-queue/ORD_MED_001/mark \
  -H "X-API-Key: payshield-dev-key-2026"

# Simulator (basic vs premium)
curl -s -X POST http://localhost:8000/v1/return/simulate \
  -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
  -d '{"amount":12000,"category":"electronics","payment_method":"UPI","user_return_rate_30d":0.05,"user_return_rate_90d":0.08}'

# Guided demo guide
curl -s http://localhost:8000/v1/meta/demo/guide -H "X-API-Key: payshield-dev-key-2026"
```
```

---

## 4. Completed work — guided demo, review queue, simulator

### Guided Demo Mode ✅

| Commit | What |
|---|---|
| `519c463` `feat(api): add guided-demo script endpoint` | `GET /v1/meta/demo/guide` returns the 10-minute judge tour — five stops (cost model, return-risk scoring, waterfall explainability, abuse-ring/fraud, Track 2 compliance), each mapped to a real dashboard route with a live description and action. Auth-gated; 3 integration tests |
| `11edb16` `feat(dashboard): add guided demo tour page` | `/demo-tour` walks the script with a progress bar, per-stop card, Previous/Next/Open controls and a countdown that auto-navigates to the real surface; "Start Demo" button in the sidebar. TS/Vite build passes |

### Human-Review Queue ✅

| Commit | What |
|---|---|
| `ea1e7c1` `feat(api): add human-review queue endpoints` | `GET /v1/meta/review-queue` lists the latest 10 MEDIUM return-risk decisions straight from the tamper-evident audit chain (never fabricated), newest-first, de-duplicated, with a per-order `reviewed` flag in Redis; `POST /v1/meta/review-queue/{order_id}/mark` toggles it. 3 integration tests |
| `a5c25ff` `feat(dashboard): add human-review queue page` | `/review-queue` table with pending/reviewed badges, a pending-count, and one-click Mark-as-Reviewed. Sidebar link added |

### Calibration Simulator ✅

| Commit | What |
|---|---|
| `3cd5d03` `feat(api): add return-risk calibration simulator endpoint` | `POST /v1/return/simulate` scores an arbitrary feature vector (amount/AOV, rates, days-since, device, category, method) against the **basic** (7-feature) or **premium** (9-feature) model — the stage toggle swaps the real models, so it shows how better data changes the score, not a hardcoded offset. Ratio capped to the training envelope. 4 integration tests |
| `4d1b3b2` `feat(dashboard): add calibration simulator page` | `/simulator` sliders + Basic/Premium toggle with live debounced scoring, score/tier and the feature vector rendered live. Sidebar link added |
| `5e02733` `feat(api): mark guided demo, review queue and simulator verified in the compliance map` | Compliance map now **20/20 verified**; test asserts no requirement is left planned |

**Live verification (Docker stack):** review queue lists the latest MEDIUM decisions and a mark reflects immediately; simulator returns 7 vs 9 features for basic/premium; demo guide serves 5 stops; `verify_live_stack.py` → 11/11; compliance → 20/20.

---

## 5. Honest gaps / known caveats

1. **Model not trained on live-distributed features.** The demo path is aligned
   and verified 11/11, but the production scorer is still the offline-DGP model.
   Recalibrating on real (or live-shaped) merchant data is "What I'd Do Next" #1
   — the API already logs `xgb_features` per scored order to build that dataset.
2. **Synthetic data.** All labels come from the calibrated DGP, not real orders.
3. **No live pilot yet.** The 0.50 gate and base-rate calibration are projections.
4. **Razorpay disputes live codec pending.** Schema tested against the real API;
   live dispute payloads not yet exercised (no disputes exist on the test account).

---

## 6. Commit-log convention used

Each phase ships as its own conventional commit (never a "phase 1/2/3" message):

- `docs(judges): ...` — documentation/narrative
- `feat(api): ...` — backend endpoint
- `feat(dashboard): ...` — frontend page
- `fix(...)`, `test(...)` — as appropriate per change

Future phases should follow the same rule: one commit per logical unit, a clear
conventional message, and a push after each.

---

_Repo root for all paths above. Latest commits on `master`; remote `origin` is up to date._
