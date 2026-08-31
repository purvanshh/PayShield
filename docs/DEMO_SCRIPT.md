# PayShield Track 2 — Demo Script (Return-Risk)

Six scenes, ~4:30 total, ready to record. Every number below comes from a
measured run (seeded-demo verification, `--full-verify`) — nothing is
aspirational; if a number changes, the script changes with it. Track 2 is
**return-risk**: fraud and chargeback extensions exist in the repo but are out
of scope here. The dashboard's **Start Demo** button runs this exact tour
interactively.

## Setup (before recording)

```bash
# 1. Start the stack (api + redis + dashboard)
docker compose -f docker/docker-compose.yml up -d --build

# 2. Seed Redis with curated demo profiles + audit records
python scripts/seed_demo_data.py

# 3. Verify health
curl -s http://localhost:8000/health | python -m json.tool

# 4. Open the dashboard at http://localhost:3000 (admin / admin), click Start Demo
```

## Scene 1 — Return-Risk Scoring, the serial returner (0:00–0:45)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/return/score \
  -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
  -d '{"order_id":"ORD_SERIAL_001","user_id":"U_SERIAL_001","merchant_id":"M_FASHION_001",
       "amount":5500,"category":"fashion","payment_method":"UPI","cod_flag":true}'
```

**Expected output:** `risk_tier: HIGH`, `return_risk_score ≈ 0.94`,
`engine: xgboost`, `R-RULE-01` (serial returner) + `R-RULE-03` (COD refusal)
fired, recommendations include prepaid-only + manual review.

**Talking points:** the XGBoost model scores before dispatch; the response
also carries `model_path` and the exact feature vector — the judge can see
which evaluated model ran and what went in.

## Scene 2 — The honest customer (0:45–1:30)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/return/score \
  -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
  -d '{"order_id":"ORD_HONEST_001","user_id":"U_HONEST_001","merchant_id":"M_ELECTRONICS_001",
       "amount":12000,"category":"electronics","payment_method":"UPI","cod_flag":false}'
```

**Expected output:** `risk_tier: LOW`, `return_risk_score ≈ 0.03`.

**Talking points:** every feature in `feature_breakdown` carries
`value · weight · contribution · source` — we can explain the score down to
the penny (see `docs/DEMO_DATA.md`). This is the false-positive story: a
clean profile just clears.

## Scene 3 — Explainability: the Model Waterfall (1:30–2:30)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/return/explain \
  -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
  -d '{"order_id":"ORD_SERIAL_001","user_id":"U_SERIAL_001","merchant_id":"M_FASHION_001",
       "amount":5500,"category":"fashion","payment_method":"UPI","cod_flag":true}'
```

**Expected output:** `return_risk_score`, `risk_tier`, `base_score: 0.5`, and
a `waterfall` — per-feature `value · importance · contribution` sorted by
contribution, with the honest note that the attribution is approximate
(gain importance × normalized value; the model output is nonlinear).

**Talking points:** the dashboard shows this as horizontal bars under
**Model Waterfall** — which features drove the score and by how much. No
black box.

## Scene 4 — Abuse-ring sentinel (2:30–3:15)

**Command:** score the four seeded ring users with `shipping_address.pincode = 560037`:

```bash
for i in 001 002 003 004; do
  curl -s -X POST http://localhost:8000/v1/return/score \
    -H "X-API-Key: payshield-dev-key-2026" -H "Content-Type: application/json" \
    -d "{\"order_id\":\"ORD_RING_$i\",\"user_id\":\"U_RING_$i\",\"merchant_id\":\"M_FASHION_001\",
         \"amount\":5000,\"category\":\"fashion\",\"payment_method\":\"UPI\",\"cod_flag\":false,
         \"shipping_address\":{\"pincode\":\"560037\"}}"
done
```

**Expected output:** `U_RING_001..003 → LOW 0.113`; `U_RING_004 → HIGH 0.85`
with `R-RULE-09` triggered.

**Talking points:** the model alone rates every ring user LOW — the shared
address + return-velocity spike is what the **abuse-ring sentinel** catches
(score floor to HIGH, defense-only: require prepaid, never a block). This is
coordinated-abuse detection on the return-risk surface.

## Scene 5 — Reproducibility (3:15–3:45)

**Command:**

```bash
python scripts/run_all_scenarios.py --full-verify
```

**Expected output:** `ALL CHECKS PASS — submission ready.` (11/11).

**Talking points:** every headline number — PR-AUC 0.7991 → 0.9497 across the
three maturity stages, ₹17.4L → ₹53.5L/month — reproduces from one command on
a fully pinned Python 3.11 stack. The suite also verifies temporal integrity
(no look-ahead) and doc/manifest consistency. 498 tests pass.

## Scene 6 — Closing (3:45–4:30)

- **Problem:** Indian e-commerce loses real money to returns; a wrong review
  flag costs ₹200 of operator time, a wrong prepaid block ₹3,180 — both
  modeled, not hand-waved.
- **Why synthetic:** evaluated public datasets, rejected for distribution
  mismatch (no COD, different reasons/logistics), then calibrated to Indian
  distributions — see `docs/SIMULATOR_VALIDATION.md`.
- **Honesty:** the live demo runs a model trained on the live feature pipeline
  (test PR-AUC 0.8227); headline metrics are the evaluated DGP hold-out
  (`docs/CALIBRATION_GAP.md`).
- **Failure recovery:** fresh users and Redis outages degrade to conservative
  priors with capped confidence and a provenance trail
  (`docs/GRACEFUL_FAILURE.md`).

## Timing checkpoints

| Time | Checkpoint |
|---|---|
| 0:45 | Scene 1 done — HIGH tier + rules visible |
| 1:30 | Scene 2 done — LOW tier + breakdown visible |
| 2:30 | Scene 3 done — Model Waterfall visible |
| 3:15 | Scene 4 done — ring caught at HIGH 0.85 |
| 3:45 | Scene 5 done — ALL CHECKS PASS on screen |
| 4:30 | Scene 6 done — closing the loop |
