# Return & Refund Risk Patterns — Research Reference

**Track 02 (AI Risk Manager) — Phase 2**
**Scope:** Indian e-commerce return rates, return-fraud patterns, UPI refund mechanics.

---

## 1. Category Return-Rate Baselines (India, e-commerce)

| Category | Typical return rate | Notes |
|---|---|---|
| Fashion / apparel | 25–40% | Sizing mismatch dominates; wardrobing cluster |
| Footwear | 20–30% | Size/fit abuse, false-to-size |
| Electronics | 8–15% | Defect-driven, higher *fraud* share per rupee |
| Groceries | 2–5% | Perishability; low tolerance for damage |
| Beauty / personal care | 10–20% | Hygiene-conscious "changed mind" returns |
| Furniture / large items | 3–8% | Pickup-only; restocking friction |

**Why it matters:** a `0.35` user return rate is *normal* in fashion, *extreme* in
groceries. The scorer must compare against the **category baseline**, not the
merchant's global mean. That is why PayShield's feature registry stores
`merchant_return_rate_by_category` and `txn_category_return_baseline`
(the `category` attribute of the scoring request).

---

## 2. Return-Fraud Patterns Specific to India

| Pattern | Definition | PayShield feature signal |
|---|---|---|
| **Wardrobing** | Buy fashion, wear (event), return clean/near-clean | `user_return_reason_distribution` skew + repeat same-category returns; `user_serial_returner_flag` |
| **Empty-box returns** | Customer claims box empty; return pickup scan mismatch | merchant-side `proof_of_return` quality; `txn_order_value` vs refund delta |
| **Serial returner** | >50% return rate with >3 lifetime orders | `user_serial_returner_flag`; `user_return_rate_30d/90d` |
| **COD refusal** | Order dispatched COD, refused at door | `user_cod_refusal_rate`; fulfillment loss, not a return |
| **Size/fit abuse** | Order multiple sizes, return non-fitting | return velocity per user per category; `user_return_velocity_7d` |
| **Return fraud ring** | Same address/phone/device returns many merchants | merchandized via graph evidence in L2 (return events on the shared device) |

**Red-flag list (rule candidates → `return_risk_rules.yaml`):**
- `user_return_rate_30d > 0.30 AND total_orders > 3` → serial returner → `FLAG_FOR_REVIEW`.
- `amount > 3000 AND category == fashion AND user_return_rate_30d > 0.20` →
  → `REQUIRE_PREPAID_ONLY`.
- `user_cod_refusal_rate > 0.4` → `REQUIRE_PREPAID_ONLY`.
- `user_return_velocity_7d >= 3 AND same category` → `FLAG_FOR_REVIEW`.
- Late-night high-value fashion + first-time user → `CAP_QUANTITY_2` (soft).

Timing: **75% of returns happen within 14 days**, so a *lookback* of 30–90 days
for user profiles (config `feature_lookback_days: 90`) is sufficient and keeps
Redis small.

---

## 3. Razorpay Refund / Return Capabilities

- **Instant refunds** (Razorpay route + UPI "Rev" reversal): instant for the
  merchant, asynchronous settlement for the payer PSP.
- **Partial refunds** are supported per payment; repeated refund attempts are
  possible while `amount <= paid amount`.
- Refund webhook: `refund.created` / `refund.processing` — carries
  `payment_id`, `refund_id`, `amount`, `notes`, `status`, `utr` when processed.

**PayShield hook:** the `refund.created` webhook (`POST /v1/events` style) is the
natural ingestion point for the return-risk store: on refund, PayShield updates
`return_risk:user:{user_id}` increments (returns, reason from `notes`, value) and
the merchant zset. Note `notes` is free text the merchant control — reason mapping
(`DEFECTIVE | SIZE_ISSUE | CHANGED_MIND | ...`) must be normalised from it (the
`normalize_return_reason()` helper lives in `api/schemas/return_risk.py`).

---

## 4. UPI Refund Mechanics

- UPI refunds use **cash-reversal ("Rev")** transaction types — they are **not**
  instant like card reversals; the payer PSP renders ledger movement through
  settlement cycles (typically T+0/T+1 for `Rev`, slower for failed-pull cases).
- Cancelled/expired P2A collects auto-refund through the PSP stack; the
  merchant-side signal is the **refund state machine** (`refund.created` →
  `refund.processing` → `refund.partially_refunded`/`refund.processed` →
  `refund.failed`).
- **Timing signal for risk scoring:** an order that is still unpaid 30 min after a
  COD dispatch is a high COD-refusal probability. PayShield's return-risk scorer
  consumes COD flags at checkout time, but the **fulfillment-time** restructure
  uses the webhook stream.

---

## 5. Feature Taxonomy (top level — full YAML in `configs/feature_registry_return.yaml`)

```
user_*     return_rate_30d, return_rate_90d, return_rate_lifetime,
           avg_return_value, max_return_value, return_reason_distribution,
           cod_refusal_rate, serial_returner_flag, return_velocity_7d,
           first_return_days, return_pattern_score

merchant_* return_rate_30d, return_rate_by_category,
           avg_resolution_time_hours, return_fraud_rate

txn_*      category_return_baseline, amount_risk, cod_flag,
           time_of_day_risk, is_salary_day, user_merchant_interaction_count
```

## 6. Sample Refund Webhook Payload (synthesized)

```json
{
  "entity": "event",
  "event": "refund.created",
  "payload": {
    "refund": {
      "id": "rfnd_2VzK1a",
      "payment_id": "pay_2RzD5mK9bL",
      "amount": 1500,
      "currency": "INR",
      "status": "processing",
      "notes": { "return_reason": "SIZE_ISSUE", "return_sku": "JEANS_002" },
      "created_at": 1768842000
    }
  }
}
```

**Design consequence:** `notes.return_reason` is the free-text to normalise from —
default `OTHER` when missing; unknown reasons raise no error, they only lower the
`return_pattern_score`.

---

## 7. Validated Measurement Plan (Phase 19 preview)

The scorer will be evaluated on a held-out synthetic set with the following cut
(industry-style):

- Recall @ top-10% risky orders ≥ 0.85 (catch the serial returners before dispatch)
- False-positive cost: blocking a genuine order costs ₹85 (avg. margin), issuing a
  COD refusal costs ₹160 (round-trip) — the demo needs honest per-txn cost numbers.
