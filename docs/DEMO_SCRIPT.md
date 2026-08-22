# PayShield Track 2 — Demo Script

Six scenes, ~4:30 total, ready to record. Every number below comes from a
measured run (benchmark JSON, seeded-demo verification) — nothing is
aspirational; if a number changes, the script changes with it.

## Setup (before recording)

```bash
# 1. Start the stack
make up

# 2. Seed Redis with curated demo profiles + audit records
python scripts/seed_demo_data.py

# 3. Verify health
curl -s http://localhost:8000/health | python -m json.tool

# 4. Open Swagger UI at http://localhost:8000/docs
# 5. Keep curl commands pre-typed in a scratch file for copy-paste
```

## Scene 1 — Transaction Scoring (0:00–0:45)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/score \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "txn_id": "TXN_CLEAN_001",
    "user_id": "U_CLEAN_001",
    "merchant_id": "M_FASHION_001",
    "amount": 2500.00,
    "timestamp": "2026-08-21T10:00:00",
    "device_fingerprint": "DEV_CLEAN_001",
    "location": {"lat": 19.0760, "lon": 72.8777},
    "mcc_code": "fashion",
    "txn_type": "P2M"
  }'
```

**Expected output:** `decision: ALLOW`, low `fraud_probability`, `latency_ms` in single digits.

**Talking points:** L1 velocity/geo/Benford run first (sub-ms); L2 GNN is
*conditional* — runs only when the user has graph history; L3 LLM narrative
is async via Celery and never blocks the response.

## Scene 2 — Return Risk Scoring (0:45–1:30)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/return/score \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD_SERIAL_001",
    "user_id": "U_SERIAL_001",
    "merchant_id": "M_FASHION_001",
    "amount": 5500.00,
    "currency": "INR",
    "category": "fashion",
    "payment_method": "UPI",
    "cod_flag": true
  }'
```

**Expected output:** `risk_tier: HIGH`, `R-RULE-01` + `R-RULE-03` fired,
recommendations include prepaid-only + manual review.

**Talking points:** every feature in `feature_breakdown` carries
`value · weight · contribution · source` — we can explain 0.79 down to the
penny (see `docs/DEMO_DATA.md` for the exact arithmetic).

## Scene 3 — Chargeback Response (1:30–2:30)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/chargeback/respond \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "dispute_id": "CB_WINNABLE_001",
    "payment_id": "pay_CLEAN_001",
    "transaction_id": "TXN_CLEAN_001",
    "network": "VISA",
    "reason_code": "10.4",
    "reason_description": "Fraud - Card Not Present",
    "response_deadline": "2026-09-20T00:00:00"
  }'
```

**Expected output:** `response_type: REJECT`, confidence ≥ 0.85,
`razorpay_payload` with the contest flag and evidence slots.

**Talking points:** evidence is reconstructed from the tamper-evident audit
chain (nothing re-analysed); the narrative comes from the same LLM stack
with a chargeback-specific prompt; the draft is *not* auto-submitted —
submission is `chargeback:admin` only (human-in-the-loop).

## Scene 4 — Metrics (2:30–3:15)

**Command:**

```bash
python scripts/benchmark_return_risk.py
```

**Expected output (canonical run, `models/return_risk_benchmark_results.json`):**

```
HIGH(op 0.7): P=1.0000 R=0.3675 F1=0.5375 PR-AUC=0.9806 ROC-AUC=0.9846
MEDIUM+(op 0.3): P=0.9444 R=0.9125 F1=0.9282
```

**Talking points:** 10k synthetic orders, chronological per-user hold-out
(an order score never sees future returns); PR-AUC leads because the
positive class is 40% of the test set and ranking quality is what a
merchant actually buys; both operating points are reported at the shipped
tier boundaries — no cherry-picking.

## Scene 5 — Failure Recovery (3:15–3:45)

**Command:**

```bash
curl -X POST http://localhost:8000/v1/chargeback/respond \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "dispute_id": "CB_FAIL_001",
    "payment_id": "pay_FAIL_001",
    "transaction_id": "TXN_NONEXISTENT"
  }'
```

**Expected output:** `404` with `CHARGEBACK_TRANSACTION_NOT_FOUND`-style
detail, plus a second half of the scene — the *weak case* against a real
new-user transaction:

```bash
curl -X POST http://localhost:8000/v1/chargeback/respond \
  -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{
    "dispute_id": "CB_WEAK_001",
    "payment_id": "pay_NEW_001",
    "transaction_id": "TXN_NEW_001",
    "network": "UPI",
    "reason_code": "FRAUD",
    "reason_description": "Fraudulent Transaction",
    "response_deadline": "2026-08-28T00:00:00"
  }'
```

**Expected output:** conservative `ACCEPT`/`PARTIAL` with low confidence and
warnings — "graph evidence incomplete", "LLM investigation report not
available". We show this case deliberately: when the evidence isn't there,
the system says so.

## Scene 6 — Closing (3:45–4:30)

- Problem taste: chargeback + return-fraud losses are a real Indian
  e-commerce pain; the demo uses UPI/Visa/MC reason codes and network
  deadlines, not generic ones.
- Build quality: 530+ tests, clean ruff on new modules, hermetic tests
  (no real Redis/Neo4j/Ollama needed).
- AI judgment: rules for the sub-ms decisions, GNN for relational fraud,
  LLM for narrative — each tool where it fits, with honest confidence
  everywhere.
- Failure recovery: the weak-case scene is the "what broke, how you got
  out" moment.

## Timing checkpoints

| Time | Checkpoint |
|---|---|
| 0:45 | Scene 1 done — decision displayed |
| 1:30 | Scene 2 done — HIGH tier + rules visible |
| 2:30 | Scene 3 done — REJECT + payload visible |
| 3:15 | Scene 4 done — benchmark numbers on screen |
| 3:45 | Scene 5 done — 404 + weak case shown |
| 4:30 | Scene 6 done — closing the loop |
