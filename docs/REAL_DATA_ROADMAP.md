# Real Data Roadmap

One page. Three phases. The difference between a hackathon submission and a
product is knowing what "done" actually looks like — this is the honest path
from a calibrated simulator to a validated production scorer.

## Phase 1: Hackathon (Completed)

- Calibrated synthetic DGP with hidden confounders the model never observes.
- Stage 1 floor: **PR-AUC 0.7991** · projected savings **₹17.4L/month**
  (fashion, 0.50 gate).
- Validated the pipeline against real Indian retail history (4,200 orders)
  and a reconstructed Amazon India 2025 report — see
  [`REAL_DATA_VALIDATION_RETROSPECTIVE.md`](REAL_DATA_VALIDATION_RETROSPECTIVE.md)
  and [`SIMULATOR_VALIDATION.md`](SIMULATOR_VALIDATION.md).

## Phase 2: Pilot (Next 30 Days)

- **Target:** 1,000 real orders from 1 Razorpay merchant.
- **Validate:**
  - return rate matches the 18% assumption,
  - feature importances align with the simulated ranking.
- **Output:** a **calibrated cost model**, not a retrained model — the gate
  and ₹ figures get re-based on observed numbers first.

## Phase 3: Recalibration (Next 60 Days)

- Retrain XGBoost on enriched feature distributions (Redis-backed velocity,
  geo, device).
- Close the calibration gap documented in
  [`CALIBRATION_GAP.md`](CALIBRATION_GAP.md).
- A/B test the 0.50 review gate vs. baseline (no scorer) on live orders —
  the champion/challenger harness (`ml/ab_testing.py`) is already built.

---

_Every knob in Phase 2/3 is parameterised in the generator and cost model
(`docs/SIMULATOR_VALIDATION.md` §4) — nothing requires a redesign._
