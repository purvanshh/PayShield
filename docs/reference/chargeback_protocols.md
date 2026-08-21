# Chargeback Dispute Protocols — Research Reference

**Track 02 (AI Risk Manager) — Phase 1**
**Scope:** NPCI DRF, Razorpay disputes API, Visa/Mastercard reason codes, RBI timelines.

> **Verification note (buildathon integrity).** This matrix encodes the shape of
> each network's dispute flow from public documentation. Exact decimal codes,
> field names and deadlines drift — Razorpay's own docs URL used in the original
> plan (`/docs/api/payments/chargebacks/`) now 404s in favour of
> `/docs/api/payments/disputes/`. Re-verify the live spec before wiring the
> submit path (Phase 11). What does **not** change is the *structure*: a rebuttal
> is a dispute ID + merchant response + evidence bundle + narrative, and that is
> what PayShield's evidence collector is built around.

---

## 1. NPCI UPI Dispute Resolution Framework (DRF)

NPCI's UPI DRF governs dispute handling between banks over UPI transactions. Key facts:

- **Dispute initiation** happens through the payer bank (customer raises a dispute
  with their PSP/bank), which then moves to NPCI's dispute portal.
- Disputes are bucketed by **claim type**, the two most relevant for merchants:
  - **Customer Refund (CR)** — customer claims money taken but order/service not
    delivered; UPI Refund (rev) against COD/debit orders.
  - **UPI Non-Completion (UNC)** — funds debited but the recipient PSP not
    credited (failure at the Rev/collect intent level).
  - **Unauthorized transaction** — customer did not authorise the debit;
    adjudicated under RBI's limited-liability framework (see §4).
- Each claim type has **reason codes** that describe the disputed condition, and
  every dispute has a **resolution status lifecycle**:
  `OPEN -> INITIATED -> RESPONSE -> PROCESSED (accepted / rejected / partially accepted)`.
- **Response window:** merchant-side (PSP/merchant-bank) response windows are short
  — typically **hours to a few days** depending on claim type, and are enforced by
  automatic adverse resolution of the payer: **failed to respond => money returned**.
  This is why the PayShield `response_urgency` signal is scored from the deadline,
  not from an arbitrary priority.

**Implication for PayShield:** UPI chargebacks are the *most* urgent and the *least*
evidenced (no physical delivery record). The UPI row in `response_deadline_days`
should be a single-digit window, and evidence completeness gates the
ACCEPT/REJECT decision hard.

---

## 2. Razorpay Disputes (Chargebacks) API

Razorpay exposes disputes under the **Disputes** resource. Entity and endpoints:

### `GET /v1/disputes` / `GET /v1/disputes/{id}`

Dispute entity (abridged fields used by PayShield):

```json
{
  "id": "disp_2Vw9aZ0q3X",
  "entity": "dispute",
  "payment_id": "pay_2RzD5mK9bL",
  "amount": 4500,
  "currency": "INR",
  "status": "accepted",
  "reason_code": "U07",
  "reason_description": "Cardholder fraud probe",
  "action": "action_8A9BcD2EfG",
  "settlement_id": "settle_2Ab8",
  "contact": { "name": "", "phone": "", "email": "" },
  "created_at": 1768752000
}
```

Status values include `open`, `accepted`, `contested`, `partially_accepted`,
`partially_contested`, and `closed` (final).

### `POST /v1/disputes/{id}/contest`

Contests a dispute (i.e., REJECT the customer claim):

```json
{
  "contest": true,
  "evidence": {
    "amount": 4500,
    "summary": "Transaction was legitimate; device fingerprint and delivery proof available",
    "billing_proof": [
      { "type": "document", "url": "https://s3/.../invoice.pdf", "description": "Invoice" }
    ],
    "shipping_proof": [
      { "type": "document", "url": "https://s3/.../courier.pdf", "description": "Courier scan" }
    ],
    "proof_of_delivery": [
      { "type": "document", "url": "https://s3/.../pod.jpg", "description": "Proof of delivery" }
    ],
    "proof_of_service": [],
    "proof_of_refund": [],
    "cancellation_proof": [],
    "proof_of_defect": [],
    "proof_of_dispatch": [],
    "cancellation_by_customer": [],
    "customer_communication": [
      { "type": "document", "url": "https://s3/.../chat.pdf", "description": "WhatsApp confirmation" }
    ],
    "customer_confirmation": [],
    "third_party_validation": [],
    "proof_of_manufacture": [],
    "other": []
  }
}
```

Every evidence slot takes an **array** of `{ "type": "document" | "file", "url",
"description" }` objects — `document` for hosted (URL) attachments, `file` when
uploaded to Razorpay's file endpoint first.

### `POST /v1/disputes/{id}/accept`

Accepts the dispute (i.e., agrees with the customer claim):

```json
{ "accept": true, "comment": "Order cancelled by customer" }
```

**Auth:** Basic Auth with `key_id:key_secret`, `X-Razorpay-Merchant-Id: <merchant>`
header in aggregate/payout-account flows.

> **Latest docs URL check required before Phase 11.** The migration from
> `/chargebacks` to `/disputes` and the `contest.accept` split is why the
> `razorpay_client.py` module keeps payload construction in **one function**
> (`_build_razorpay_payload` in the rebuttal builder). If Razorpay renames a field,
> that one function changes and nothing else does.

---

## 3. Card Network Reason Codes

Merchant-side evidence standards differ per code. Common codes:

### Visa

| Code | Meaning | Shared evidence requirements |
|------|---------|------------------------------|
| 10.4 | Fraud — no cardholder authorization | Auth record, IP/device consistency, AVS/CVV 2CND, velocity proof, customer communication |
| 10.5 | Fraud — card-activated telephone txn | Voice identification records, phone number match, billing address match |
| 11.1 | Cardholder dispute — not as described | Item description, photos, return policy, customer communication |
| 11.2 | Cardholder dispute — credit card not received | Dispatch proof, address verification, customer communication |
| 12.1 | Merchandise not received | Dispatch + proof of delivery, tracking, customer communication |
| 13.1 | Services not provided | Service contract, proof of service, completion record |
| 13.2 | Cancelled recurring transaction | Cancellation records, prior mandates |
| 13.6 | Credit not processed | Refund/credit record, timestamps |
| 13.9 | Defective merchandise | Defect photos, inspection report, repair/replacement records |

### Mastercard

| Code | Meaning | Shared evidence requirements |
|------|---------|------------------------------|
| 4831 | Cardholder dispute — fraud | As Visa 10.4 |
| 4834 | Cardholder dispute — POI error | Terminal/txn log, total sale amount record |
| 4840 | Fraud — no authorization | Auth response, AVS, device/IP consistency |
| 4841 | Duplicate processing / duplicate txn | Unique txn ID, reversal records |
| 4856 | Merchandise not received | Dispatch, POD, tracking |
| 4859 | Goods or services not provided | Contract, proof of supply |
| 4863 | Cardholder dispute — not as described | Description, photos, policy |
| 4870 | Cardholder dispute — credit not processed? | (verify) |

A **fraction of the exact code tables are listed intentionally**: for the
buildathon the decisive columns are (a) which evidence *category* satisfies each
code and (b) that accepted file types are documents/PDF/scan — this is what drives
the `reason_code -> required_evidence` matrix in §5.

---

## 4. RBI Timelines (Customer Protection in Digital Payments)

Applicable to chargeback urgency:

- **Unauthorized debit (customer) liability is capped** per the RBI circular on
  customer protection in digital payments (limited liability model): no liability
  for customer-reported unauthorized P2A-type transactions when there is no
  customer negligence; refund in **up to 4 operative days** from complaint
  (the date the bank must provisionally credit).
- **T+60/T+120** — card network filing windows generally permit merchants/card
  associations to process claims within 60–120 days of the transaction, but
  *participant response windows* are as short as **15–30 days** for Visa/MC and
  **days** for UPI DRF.
- RBI's "know everything day" / data-locality rules justify the tamper-evident
  audit chain: **evidence must be reconstructible 120+ days after the txn**.

**Consequence for PayShield:** every evidence bundle must be tagged with
`generated_at` and the response must report `response_urgency` computed against
(`response_deadline - now`) / network window, so the queue prioritises disputes
whose deadline is closest.

---

## 5. Evidence Requirement Matrix

> Mapping table version "1.0.0". Columns: `required` = mandatory categories,
> `optional` = boosts confidence, `file_types` = accepted.

| Reason code | Network | Required evidence | Optional evidence | File types |
|---|---|---|---|---|
| 10.4 / 4831 | Visa / MC | transaction proof, auth record, device fingerprint | velocity proof, IP geolocation, graph evidence | PDF, JSON export, screenshots |
| 12.1 / 4856 | Visa / MC | dispatch proof, proof of delivery, tracking | customer communication, address history | PDF, scan, courier receipts |
| 13.1 / 4859 | Visa / MC | proof of service, contract record | customer communication, delivery proof | PDF, SOW, e-sign records |
| 13.6 / 4870 | Visa / MC | refund proof, settlement id, timestamps | return policy | PDF, settlement exports |
| CR (Customer Refund) | UPI | txn proof, refund/rev status | velocity proof, device fingerprint | JSON export, screenshots |
| UNC (Non-Completion) | UPI | PSP credit logs, UTR, settlement id | velocity proof | JSON export, bank statement lines |

### Accepted file types (network-agnostic)

`document` (PDF, JPEG/PNG scans), `file` (uploaded binaries), `json` (API exports
for proof-of-authorization audits). Video/audio accepted under specific Visa codes
(e.g., voice-identification in 10.5 handsets).

> **Critical honesty rule:** where evidence is absent, PayShield's rebuttal builder
> downgrades to `PARTIAL`/`ACCEPT` rather than fabricating documents. A fabricated
> evidence URL is a chargeback fraud charge — the completeness score exists to make
> that risk explicit.

---

## 6. Field Mapping Table

| PayShield | Razorpay API | NPCI/Visa |
|---|---|---|
| `txn_id` (internal) | `payment_id` | UTR / reference nr |
| `dispute_id` (webhook) | `disputes.id` | dispute reference |
| `amount: Decimal` | `evidence.amount` | claimed amount |
| `txn_timestamp` | `payment_details.paid_at` | txn date |
| `response_type REJECT` | `contest: true` (= REJECT) | reject / respond |
| `response_type ACCEPT` | `accept: true` | accept |
| `response_type PARTIAL` | `partially_contested` | partial |
| `attachment.evidence_type` | `evidence.<slot>` | rule-based category |
| `Attachment.url` | `{url, type: document, description}` | carrier `document` |
| `Token (auth)` | Basic Auth + merchant header | PSP-level signature |
| `audit_trail[].action` | `summary` evidence slot *mirrors* | narrative field |

---

## 7. Sample Rebuttal (anonymized, synthesized — not a real acceptance)

```json
{
  "dispute_id": "disp_2Vw9aZ0q3X",
  "payment_id": "pay_2RzD5mK9bL",
  "transaction_id": "TXN-2026-08121-000117",
  "network": "VISA",
  "reason_code": "10.4",
  "reason_description": "Cardholder fraud probe",
  "response_type": "REJECT",
  "response_urgency": 0.62,
  "confidence_score": 0.87,
  "evidence_completeness": 0.92,
  "razorpay_payload": {
    "contest": true,
    "evidence": {
      "amount": 4500,
      "summary": "Device fingerprint hash 6a1f… matches 47 prior sessions; velocity profile is within the user baseline; 3DS validity check passed.",
      "billing_proof": [
        { "type": "document", "url": "https://ship.payshield.io/ev/txn_117_invoice.pdf", "description": "Invoice" }
      ],
      "proof_of_delivery": [
        { "type": "document", "url": "https://ship.payshield.io/ev/txn_117_pod.jpg", "description": "Proof of delivery" }
      ],
      "customer_communication": [
        { "type": "document", "url": "https://ship.payshield.io/ev/txn_117_chat.pdf", "description": "Customer confirmed receipt via WhatsApp" }
      ]
    }
  }
}
```

> The evidence URLs above use PayShield's (planned) secure-attachment bucket
> (`ship.payshield.io/ev/…`) — final submission wires real presigned URLs from
> Phase 11's `razorpay_client`.
