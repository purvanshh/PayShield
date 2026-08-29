# PayShield — Track 2 Execution Report

**Date:** 2026-08-29 · **Status:** Phase 0 ✅ complete, Phase 1 ✅ complete ·
**Branch:** `master`

This report is the living status of the Track 2 execution plan. It records
what is achieved, the evidence, and exactly what remains — so the next working
session can pick up without re-deriving context.

---

## 1. Headline status

| Area | Status | Evidence |
|---|---|---|
| Hermetic ML verification | **10/10 PASS** | `python scripts/run_all_scenarios.py --full-verify` → `ALL CHECKS PASS` |
| Live Docker stack | **11/11 PASS** | `seed_demo_data.py` + `verify_live_stack.py` |
| Test suite | **477 passed, 1 skipped** | `pytest tests/` (47 modules) |
| Track 2 compliance map | **14/20 verified, 6 planned** | `GET /v1/meta/track2-compliance` + `docs/TRACK2_COMPLIANCE.md` |
| Business case | **₹17.4L → ₹53.5L/month** | `docs/cost_model/calculator.py --all-maturity` |

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

---

## 3. Verification (run before any further commit)

```bash
# Hermetic (Python 3.11 + pinned requirements)
python scripts/run_all_scenarios.py --full-verify     # 10/10 PASS

# Live Docker stack
docker compose -f docker/docker-compose.yml up -d --build api redis
python scripts/seed_demo_data.py
python scripts/verify_live_stack.py                   # 11/11 PASS

# Tests
pytest tests/                                         # 477 passed, 1 skipped

# Compliance endpoint
curl -s -X GET http://localhost:8000/v1/meta/track2-compliance \
  -H "X-API-Key: payshield-dev-key-2026" | jq '.requirements | length'   # 20
```

---

## 4. What's next (remaining phases)

### Phase 2 — Feature-Waterfall Explainability (XAI) · ~2h
- **Backend:** `POST /v1/return/explain` in `api/routes/return_risk.py` —
  per-feature contribution to the score (model feature importance × feature
  value), tier, base score. Use the model's `feature_importances_` (SHAP is a
  stretch goal; deterministic approximation is fine and auditable).
- **Frontend:** collapsible "Feature Contribution" bars on the return-risk
  page.
- **Note:** the API already returns `xgb_features` and `feature_importance`;
  the endpoint formalises the waterfall.
- Commit(s): `feat(api)` + `feat(dashboard)`.

### Phase 3 — Abuse-Ring Sentinel & Temporal Integrity · ~3h
- **Abuse-ring:** track `shared_address_count` in `return_risk/feature_engine.py`
  (Redis set per address-hash); add an `abuse_ring_suspicion` rule to
  `configs/return_risk_rules.yaml` (condition + score override); wire into the
  scorer **without touching the primary model**.
- **Temporal integrity:** `scripts/verify_temporal_integrity.py` that asserts
  the DGP's per-order features use only prior orders (no look-ahead); add as a
  check to `--full-verify` (would become check 11).
- Commit(s): `feat(return-risk)` + `feat(verify)`.

### Phase 4 — Guided Demo Mode · ~6h
- **Backend:** `GET /v1/meta/demo/guide` returning the 10-minute step script.
- **Frontend:** `/demo-tour` page with a progress bar that auto-navigates to
  the cost-model, return-risk, chargeback, agents, and compliance pages.
- **Note:** the live stack already passes 11/11, so the demo is green
  end-to-end without any skip flags.

### Phase 5 — Human-Review Queue UI (optional) · ~2h
- `GET /v1/meta/review-queue` (last 10 MEDIUM orders from the audit chain +
  reviewed flag in Redis) and `POST /v1/meta/review-queue/{id}/mark`; a
  `/review-queue` page.

### Phase 6 — Calibration Simulator (optional) · ~4h
- `POST /v1/return/simulate` (feature sliders → score + tier) and a `/simulator`
  page with a Stage 1 vs Stage 3 toggle.

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
