# Chargeback Flow Tests — Coverage Notes

**Suite:** `tests/integration/test_chargeback_flow.py` (6 scenarios) plus the
route-level suites `tests/integration/test_chargeback_api.py` (9) and
`tests/integration/test_return_risk_api.py` (9). All hermetic: in-memory
Redis, directory-local audit chain, mock Razorpay.

## End-to-end scenarios

| Scenario | Expected | Covers |
|---|---|---|
| Fraud dispute (10.4), full bundle, Visa | REJECT, confidence ≥ 0.9, completeness ≥ 0.8, contest: true | happy path; audit-trail shape (action + ISO timestamp); billing_proof slot |
| Incomplete bundle (no device, no rules) | PARTIAL/ACCEPT, confidence < 0.7, graph/report None | graceful degradation; honest low-confidence draft |
| Service dispute (13.1) without delivery proof | ACCEPT | cannot-win arbitration is admitted, not contested |
| Service dispute (13.1) with delivery proof | REJECT with BlueDart POD in proof_of_delivery | merchant-evidence merge swings the verdict |
| UPI vs Visa urgency | formula matches elapsed window (1 - remaining/window); monotone in deadline | per-network windows from config |
| Mock Razorpay submission | SUCCESS envelope, mock: true, under_review | deterministic submit path without credentials |
| Generator-fed flow | chargeback from `ChargebackSyntheticGenerator` round-trips the real collector/builder | Phase 18 dataset wires into the pipeline |

## Route-level coverage (test_chargeback_api.py)

- 403 without credentials; RBAC gates (admin-only submit, auto-submit gate)
- 404 unknown txn; 404 uncached rebuttal; 200 cached retrieval
- submit: no-draft 404, dev-key 403, admin-key 200 (mock under_review)

## Return-risk route coverage (test_return_risk_api.py)

- score seeded HIGH profile (R-RULE-01 fired, prepaid recommendation,
  feature breakdown present)
- score new-user defaults (confidence < 1.0)
- 422 on non-positive amount (Decimal constraint safe after handler fix)
- update refreshes profile (counters, COD orders, reason storage)
- profile endpoint for known + new users

## What is deliberately not covered

- Real Razorpay network calls (mock transport + mock mode only; contract
  documented in `docs/reference/chargeback_protocols.md`)
- L2/L3 live inference (graph/investigation are injected stubs here — the
  collector's provider hooks take both `None` and fetched-report shapes)
- Live PostgreSQL/Neo4j (never required for the evidence responder, which
  reads the audit chain + Redis mirrors by design)
