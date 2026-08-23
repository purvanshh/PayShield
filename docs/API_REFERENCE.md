# API Reference — Track 2

The authoritative contract per endpoint. Auth = `X-API-Key` (dev default
`payshield-dev-key-2026`); all `/v1` routes share the per-key rate limit
(1000/hr) unless noted. OpenAPI fragments: `docs/reference/openapi_*.yaml`.

## POST /v1/return/score

| Field | Type | Notes |
|---|---|---|
| order_id / user_id / merchant_id | str | required |
| amount | Decimal > 0 | required |
| currency | str | default INR |
| category | str | unknown categories fall back to global baseline (0.15) |
| payment_method | enum UPI/CARD/COD/NETBANKING/WALLET | default UPI |
| cod_flag | bool | default false |
| items / shipping_address / device_fingerprint / timestamp | optional | |

**200** `{status, data: ReturnScoreResponse, latency_ms}` — the response
carries `feature_breakdown` (value · weight · contribution · source per
feature), `rules_triggered` (severity-ordered), `recommendations`,
`user_profile`, `confidence`. **422** on bad amounts (Decimal-safe
handler). **429** per-key.

## POST /v1/return/update

`user_id, order_id, amount, category, cod_flag, returned, return_reason` —
refreshes the profile (counters, velocity zset, reason distribution,
running average). `return_risk:write` permission. Audit event
`RETURN_RISK_UPDATED`.

## GET /v1/return/profile/{user_id}

Merchant-dashboard view: `total_orders/returns`, `return_rate_30d`,
`return_rate_lifetime`, `serial_returner`, `avg_return_value`,
`is_new_user`, `latency_ms`. `return_risk:read`.

## POST /v1/chargeback/respond

`dispute_id, payment_id, transaction_id` required; `network` default UPI;
`reason_code/description`, `response_deadline`, `auto_submit`,
`evidence_override` optional.

**200** — draft rebuttal: `rebuttal_id`, `response_type`
(ACCEPT/REJECT/PARTIAL), `confidence_score`, `evidence_completeness`,
`narrative {summary, full_report, key_evidence}`, `razorpay_payload`,
`audit_trail`, `warnings`. Draft cached 30d; payment→txn mapping written
so a later webhook can auto-rebuild. **404** unknown txn. **403** on
`auto_submit` without `chargeback:admin`. **422** auto-submit with
completeness below threshold. `chargeback:write`.

## GET /v1/chargeback/{dispute_id}

Cached draft by dispute id. **404** if absent/expired.

## POST /v1/chargeback/{dispute_id}/submit

`strike: contest|accept|partial`, `comment` — submits via the Razorpay
client (mock mode by default; `RAZORPAY_MOCK_MODE=false` for real).
`chargeback:admin`. Mirrors `razorpay_status` back; audit event
`CHARGEBACK_SUBMITTED`; **502** mapped from Razorpay failures.

## POST /webhooks/razorpay/chargeback

Body + `X-Razorpay-Signature` (HMAC-SHA256 of raw body with
`RAZORPAY_WEBHOOK_SECRET`, default dev secret). Event
`chargeback.created|updated|closed` → dispute marker, audit append, and
auto-rebuttal when the payment mapping exists. **400** bad signature,
**200** `{status: processed}`.

## Error model

All handlers return `{error, detail, request_id}` where `error` is a
machine code (`CHARGEBACK_TRANSACTION_NOT_FOUND`, `VALIDATION_ERROR`,
`TOO_MANY_REQUESTS`, ...). Strategy matrix in
`docs/technical/chargeback_error_handling.md`.

## Admin surfaces (Track 2 additions)

- `POST /admin/experiments/return-risk` + `.../{id}/evaluate` —
  champion/challenger weight experiments (`model:promote`).
- `GET /admin/drift/return-risk` — PSI report for the six return-risk
  features (`metrics:read`).
- `GET /admin/drift/psi` (pre-existing fraud-path drift).
