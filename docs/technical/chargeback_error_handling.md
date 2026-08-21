# Chargeback & Return-Risk API — Error Handling Strategy

**Track 02 — Phases 5/6.** Spec for the two new surfaces; wiring happens in
Phases 12/16 (router registration) but the behaviour contract is fixed here
so downstream callers can code against it now.

---

## 1. `POST /v1/chargeback/respond`

### Auth & access control
- Header `X-API-Key` (same as all **v1** routes), role → permission
  `chargeback:write` required (see `configs/rbac.yaml`).
- Human-in-the-loop: generation and submission are **separate endpoints**;
  only `chargeback:admin` may submit. This satisfies EU AI-Act style human
  oversight for high-stakes automated dispute responses.

### Rate limiting
- **100 requests/hour per API key** — disputes are infrequent and expensive
  (each generation reads the audit chain). Reuses the existing fixed-window
  limiter keyed by API-key hash (`RATE_LIMIT_API_KEY_PER_HOUR` override local
  to this route).
- 429 includes `Retry-After` header.

### Errors

| HTTP | Code | Meaning | Recovery hint |
|---|---|---|---|
| 404 | `CHARGEBACK_DISPUTE_NOT_FOUND` | dispute_id unknown in PayShield audit log | Check the Razorpay webhook payload / dispute id spelling |
| 404 | `CHARGEBACK_TXN_NOT_FOUND` | internal txn not in audit chain | Transaction pre-dates audit retention (PCI 10.x needs 12 months) |
| 422 | `INSUFFICIENT_EVIDENCE` | `completeness_score < confidence_threshold` (0.6 default) | Attach merchant evidence via `evidence_override`; never auto-reject on air |
| 429 | `TOO_MANY_REQUESTS` | per-key limit | Back off per `Retry-After` |
| 503 | `RAZORPAY_UNAVAILABLE` | `auto_submit=true` but Razorpay contested | Re-draft and submit manually later; the rebuttal is cached |

### Failure policy (fail-soft, mirroring `POST /v1/score`)
- Evidence retrieval is defensive: a Redis/audit reader hiccup produces a
  **low-completeness** rebутtal — never a 500.
- Warnings travel **inside the payload** (`data.warnings`), e.g.
  `"Graph evidence incomplete: user has <2 graph nodes"`.

---

## 2. `POST /v1/return/score`

### Auth & access control
- `return_risk:read` permission. Checkout-time call → read-only scoring, no
  mutation of state.

### Rate limiting
- **1000/hour per API key** — designed for checkout hot path; the limiter is
  the same shared mechanism as `/v1/score`.

### Errors

| HTTP | Code | Meaning |
|---|---|---|
| 422 | validation (FastAPI standard) | amount <= 0, unknown category is *allowed* (falls back to global baseline) — validated `category` only reflects literal enum? No: string, matched against registry; unmatched → baseline 0.10 |
| 429 | `TOO_MANY_REQUESTS` | over per-key limit |

- **No 404s**: a new user with no Redis profile simply scores at the
  population prior (`confidence` drops accordingly).
- Unknown category/merchant never errors — the scorer falls back to the
  global default, and the response includes the category in
  `feature_breakdown` so the merchant sees the substitution.

---

## 3. Submission endpoint (`POST /v1/chargeback/{dispute_id}/submit`)

| HTTP | Code | Meaning |
|---|---|---|
| 200 | — | Razorpay accepted (status `SUBMITTED`, mirrors razorpay_status) |
| 502 | `RAZORPAY_REJECTED` | Razorpay responded with a dispute-status rejection |
| 502 | `RAZORPAY_UNAVAILABLE` | network/5xx from Razorpay |

- The payload is **idempotent-aware**: submit re-runs with the same
  `rebuttal_id` + `dispute_id` and is tracked in `audit_trail` before and
  after (a submission is itself an audit event `CHARGEBACK_SUBMITTED`).

---

## 4. Auth/RBAC configuration summary (drifts with configs/rbac.yaml)

| Resource | read | write | admin |
|---|---|---|---|
| chargeback | analyst, admin, system | admin, system | admin |
| return_risk | analyst, admin, system | — | — |

New roles exist in `configs/rbac.yaml`: `chargeback_admin` (all three),
`return_risk_reader` (`return_risk:read`).

---

## 5. Validation rules (shared)

- **decimal amounts**: backend `Decimal`; fractional ₹ accepted, 2dp enforced
  at serialization.
- **timestamps**: `response_deadline` is naive-UTC ISO; urgency computed
  against `now(utc)` (never local time), clamped `[0,1]`.
- **network**: `UPI | VISA | MASTERCARD | AMEX | RUPAY`; unknown network →
  conservative 30-day window with a warning.
- **reason_code**: free string (network-specific codes are opaque to the
  API); the code's `required evidence` mapping lives server-side
  (`docs/reference/chargeback_protocols.md` §5).
