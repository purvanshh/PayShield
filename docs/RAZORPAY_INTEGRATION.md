# Razorpay Integration

## What This Is

PayShield is a **pre-shipping return-risk layer built on Razorpay's
infrastructure**. It is not a generic risk system — it speaks Razorpay's
event schema (`order.paid`, `refund.processed`), verifies Razorpay's
webhook signatures (HMAC-SHA256 over the raw body), consumes Razorpay's
test-mode APIs (orders, payments, refunds) and maps their fields onto the
PayShield feature engine. A merchant enables it by adding **one webhook
URL** in the Razorpay Dashboard.

## Data Flow

```
[Razorpay Checkout]
      │  order.paid webhook (HMAC-signed)
      ▼
[POST /webhooks/razorpay/return-risk]
      │  RazorpayAdapter.order_to_scoring_input()
      │    paise → INR · notes → merchant/category/cod · method → enum
      ▼
[ReturnRiskScorer]  →  LOW / MEDIUM / HIGH + transparent feature breakdown
      │
      ▼
[Merchant WMS]  →  ship · flag-for-review · require-prepaid
```

Return events flow back the same way:

```
[Razorpay refund.processed]
      ▼
[POST /webhooks/razorpay/refund]  →  return_risk:labels  →  nightly retrain
```

## Feature Mapping

| Razorpay field | PayShield feature | Notes |
|----------------|-------------------|-------|
| `order.amount` | `amount` | **paise → ₹** (`amount / 100`) |
| `payment.method` | `payment_method` | `card→CARD`, `upi→UPI`, `netbanking→NETBANKING`, `wallet→WALLET`, `cod→COD`, unknown→`UPI` |
| `order.notes.category` | `category` | merchant-configured; receipt-prefix fallback (`ELEC→electronics`, …) |
| `order.notes.cod` / method | `cod_flag` | COD orders carry the highest abuse risk |
| `order.notes.merchant_id` | `merchant_id` | resolved from dashboard notes |
| `order.notes.customer_id` | `user_id` | fallback `anon_{order.id}` |
| `order.created_at` | `timestamp` | temporal features (`hour`, `weekend`, salary-day) |
| user history (Redis) | `user_return_history_*` | accumulated from past `refund.processed` events |

The exact transformer is `integrations/razorpay_adapter.py`; sample
payloads are in `integrations/fixtures/`.

## Webhook Endpoints

| Endpoint | Event | Action |
|----------|-------|--------|
| `POST /webhooks/razorpay/return-risk` | `order.paid` | Score return risk before dispatch |
| `POST /webhooks/razorpay/refund` | `refund.processed` | Record ground-truth label for retraining |

Both reject unverified payloads with `400` before any work happens — the
webhook signature **is** the credential (same convention as the existing
`/webhooks/razorpay/chargeback`). Signature verification is a pure
constant-time HMAC compare (`chargeback/signatures.py`).

## Test-mode Orders / Payments / Refunds Client

`integrations/razorpay_orders_client.py` talks to Razorpay's test-mode API
(`https://api.razorpay.com/v1`) using the shared key pair over HTTP Basic
auth — the standard Razorpay authentication:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `create_order(payload)` | `POST /orders` | checkout-time integration |
| `get_order(id)` | `GET /orders/{id}` | scoring backfill / reconciliation |
| `fetch_payment(id)` | `GET /payments/{id}` | learn method + status |
| `create_refund(payment_id, …)` | `POST /payments/{id}/refund` | return path |

`mock_mode=True` (default for dev/tests) returns deterministic fixtures —
no network, no credentials, fully replayable. Real calls activate when
`RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` are set (test keys in `.env`).

## Production Deployment

1. Merchant adds the PayShield webhook URL in the Razorpay Dashboard.
2. Razorpay sends `order.paid` → PayShield scores in **<50 ms**.
3. PayShield returns `LOW/MEDIUM/HIGH` + the transparent breakdown.
4. The merchant's WMS acts on the recommendation before dispatch.

## Test Mode

All endpoints work against Razorpay test-mode APIs. With the test keys in
`.env`:

```bash
python -m pytest tests/unit/test_razorpay_adapter.py -v
python -m pytest tests/integration/test_razorpay_webhooks.py -v
```

Both suites run hermetic (no network): payload → feature mapping and the
signed-webhook → score/label flow are pinned by assertions.

## Winning a Chargeback (relation to the disputes client)

Dispute rebuttals reuse the same Razorpay client pattern
(`chargeback/razorpay_client.py`, mock + real) and their own signed
`chargeback.created` webhook. The return-risk scorer reduces *the number of
disputes a merchant files*; the chargeback responder improves the win rate
on the ones that do happen.