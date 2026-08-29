# Judges' Cheat Sheet — PayShield

**30 seconds, everything you need.** Full evidence in [`docs/TRACK2_COMPLIANCE.md`](docs/TRACK2_COMPLIANCE.md).

---

## What is it?

**PayShield** is a pre-shipping **return-risk scorer for Indian e-commerce**
built on Razorpay's infrastructure. It scores every order *before dispatch* and
tells the merchant **ship / review / require-prepaid** — and when a chargeback
still happens, it assembles a defensible rebuttal from evidence captured at
transaction time.

## The one number

| Surface | Measured headline | How to verify |
|---|---|---|
| **Return-risk model** (3 merchant-maturity scenarios) | Premium PR-AUC **0.9497**, basic floor **0.7991** (measured, never hardcoded) | `python scripts/run_all_scenarios.py --full-verify` → **10/10 PASS** |
| **Live stack** (Docker + Redis) | honest customer → **LOW 0.03** · serial returner → **HIGH 0.98** · suspicious burst → **BLOCK** | `seed_demo_data.py` then `verify_live_stack.py` → **11/11 PASS** |
| **Business value** | ₹17.4L/mo (fashion) → ₹53.5L/mo (premium electronics) at the 0.50 review gate | `docs/cost_model/calculator.py --all-maturity` |

## The three surfaces (one audit chain)

| Surface | Endpoint | What it does |
|---|---|---|
| **Fraud (live)** | `POST /v1/score` | L1 statistical rules (velocity/geo/device) + L2 graph + ensemble → ALLOW/BLOCK/REVIEW |
| **Return-risk (pre-ship)** | `POST /v1/return/score` | 7 features (Redis user history + txn context) → XGBoost primary, hand-weighted fallback → LOW/MEDIUM/HIGH |
| **Chargeback (remedial)** | `POST /v1/chargeback/respond` | Evidence reassembled from the tamper-evident audit chain → ACCEPT/REJECT/PARTIAL rebuttal → human-in-the-loop submit to Razorpay |

## Why it's credible (the honest list)

- **Measured, not hardcoded** — ROC-AUC via `roc_auc_score`; ablation proves every feature (both rate features = **−9.9%** PR-AUC).
- **Non-circular DGP** — labels include hidden confounders the model never sees; the base generator is `git diff`-guarded untouched.
- **Byte-reproducible** — exact pinned Python 3.11 ML stack; `--full-verify` re-runs determinism (train × 3, twice, byte-identical).
- **Explainable everywhere** — every score returns a per-feature value/weight/contribution/source; every rebuttal carries an audit trail.
- **Human-in-the-loop** — chargeback auto-submit requires `chargeback:admin`; drafts are reviewed before anything ships.
- **Honest caveats documented** — synthetic data, no live pilot yet, model not yet retrained on live-distributed features (see "What I'd Do Next").

## Verify in 60 seconds (hermetic, no Docker)

```bash
pip install -r requirements.txt          # macOS: brew install libomp
python scripts/run_all_scenarios.py --full-verify   # → ALL CHECKS PASS (10/10)
```

Live stack (needs Docker): `docker compose -f docker/docker-compose.yml up`,
then `python scripts/seed_demo_data.py`, then `python scripts/verify_live_stack.py` → **11/11 PASS**.

---

_See [`docs/TRACK2_COMPLIANCE.md`](docs/TRACK2_COMPLIANCE.md) for the requirement-by-requirement map and
[`docs/INTERVIEW_DEFENSE.md`](docs/INTERVIEW_DEFENSE.md) for prepared answers to the hard questions._
