# Track 2 Judges' Cheat Sheet — PayShield

**The 30-second hook.** Full requirement-by-requirement map: [`docs/TRACK2_COMPLIANCE.md`](docs/TRACK2_COMPLIANCE.md).

---

## 30-Second Summary

- **What it is:** a pre-shipping **return-risk scorer** for Indian e-commerce on Razorpay's
  infrastructure — plus fraud-spike detection and a chargeback evidence responder on the same
  audit chain.
- **Impact:** **₹17.4L/month** (Stage 1 fashion) → **₹53.5L/month** (Stage 3 premium electronics)
  at the 0.50 review gate — measured, reproducible.
- **Defense-only:** `MEDIUM → FLAG_FOR_REVIEW`, `HIGH → REQUIRE_PREPAID` — no autonomous blocks.
- **Honest metrics:** a wrong MEDIUM flag costs **₹200** (review time), a wrong HIGH block
  **₹3,180** (lost order) — both explicitly in the cost model.

## 5-Minute Demo

1. `python scripts/train_xgb_return_risk.py --scenario premium` → **PR-AUC 0.9497** (measured).
2. `python docs/cost_model/calculator.py --all-maturity` → **₹53.5L/month** premium electronics.
3. `python scripts/run_all_scenarios.py --full-verify` → **ALL CHECKS PASS (11/11)**,
   including a temporal-integrity check (no look-ahead in DGP/split).
4. Live Docker: `docker compose -f docker/docker-compose.yml up` → `seed_demo_data.py` →
   `verify_live_stack.py` → **11/11 PASS** (honest customer LOW 0.03 · serial returner HIGH 0.98 ·
   suspicious burst BLOCK).
5. Open `http://localhost:3000/track2-compliance` → every Track 2 requirement mapped to its
   implementation and its proof (**20/20 verified**).
6. On the Return Risk page, expand **Model Waterfall** for the XGBoost per-feature attribution;
   score the seeded `U_RING_00x` profiles with `shipping_address` pincode `560037` to watch the
   **abuse-ring sentinel** catch a coordinated ring the model rates LOW.
7. Visit **Review Queue** (the latest MEDIUM decisions from the audit chain) and the **Simulator**
   (feature sliders, Basic vs Premium model) — or hit **Start Demo** for the guided 10-minute tour.

## 10-Minute Deep Dive

1. [`EVALUATOR_GUIDE.md`](EVALUATOR_GUIDE.md) — 10-minute walkthrough of the core evidence.
2. [`BUSINESS_IMPACT.md`](BUSINESS_IMPACT.md) — the ₹17.4L → ₹53.5L business case, cost math.
3. [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md) — six mistakes + prevented ones,
   and [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md) for the debugging stories.
4. [`docs/INTERVIEW_DEFENSE.md`](docs/INTERVIEW_DEFENSE.md) — prepared answers to the hard questions.

## Why This Wins Track 2

- **Business-quantified** — ₹17.4L → ₹53.5L/month, FP/FN costs explicitly modeled (₹200 / ₹3,180).
- **Stage-maturity framework** — Stage 1 → 2 → 3 (Basic / Enriched / Premium), each a named,
  documented merchant segment; base generator git-guarded untouched.
- **Byte-reproducible** — pinned Python 3.11 ML stack; `--full-verify` runs train × 3 twice and
  asserts byte-identical results, plus a temporal-integrity check (no look-ahead).
- **Explainable everywhere** — every score returns a per-feature value/weight/contribution/source;
  `POST /v1/return/explain` adds an XGBoost feature waterfall; every rebuttal carries an audit trail.
- **Abuse-ring sentinel** — shared shipping address + return-velocity spike forces a coordinated
  ring to HIGH (defense-only), even when the model rates the user LOW.
- **15+ docs** — evaluator guide, business impact, mistakes ledger, compliance map, defense Q&A.
- **Meta-honesty** — 34 bugs fixed and tabulated in README Appendix B; the remaining calibration
  gap is documented, not hidden: [`docs/CALIBRATION_GAP.md`](docs/CALIBRATION_GAP.md).
- **Operational depth** — 4 live agents, drift monitor, audit chain, signed webhooks, human-in-the-loop
  chargeback, and a live verification suite.

---

_See [`docs/TRACK2_COMPLIANCE.md`](docs/TRACK2_COMPLIANCE.md) for the requirement-by-requirement map and
[`docs/INTERVIEW_DEFENSE.md`](docs/INTERVIEW_DEFENSE.md) for the prepared answers._
