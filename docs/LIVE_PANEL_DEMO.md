# Live Panel Demo — 10-Minute Walkthrough

Interactive variant of the video script, with an explicit "panel runs it
themselves" bias. Every file path and command below works from a fresh
clone + `make up` + `python scripts/seed_demo_data.py`.

## Minute 0–2 · Problem framing

Whiteboard: three boxes on one stem —
`[Transaction → /v1/score] (reactive)` · `[Order → /v1/return/score]
(proactive)` · `[Dispute → /v1/chargeback/respond] (remedial)`.

One line each: 18B UPI txns/month · 2–4% revenue loss on disputes ·
fashion returns 25–40% · one audit chain underneath all three.

## Minute 2–5 · Architecture deep-dive

Draw (or show `docs/diagrams/chargeback_evidence_flow.mmd` rendered):

```
webhook (HMAC) → debit marker + audit append
  → resolve payment→txn → collect_evidence(txn_id)
      └ reads SCORE_DECISION entry (point-in-time payload)
  → EvidenceBundle + completeness
  → rule-based response type (ACCEPT/REJECT/PARTIAL)
  → narrative (LLM prompt or deterministic fallback)
  → Razorpay payload (single builder)
  → draft cached; submit only via chargeback:admin
```

Say it with the two design sentences:
- The collector is **read-only** — it reconstructs transaction-time
  knowledge; it never re-analyses.
- Confidence is **diagnostic** — 1.00 means "the evidence bundle is
  complete", not "we will win".

## Minute 5–7 · Code quality evidence (screen share)

```bash
# hermetic — runs anywhere, no services
python -m pytest tests/unit/chargeback tests/unit/return_risk tests/chaos -q
# strict types + lint + security
mypy chargeback return_risk --strict --follow-imports=skip
ruff check chargeback return_risk
```

Open `tests/integration/test_chargeback_flow.py` and point at
`test_incomplete_evidence_is_conservative`: no device, no graph, no L3 →
completeness 0.62, conservative PARTIAL, warnings — 200, never a 500.

## Minute 7–9 · Metrics (screen share)

```bash
cat models/return_risk_benchmark_results.json | python -m json.tool
python -m pytest tests/ -q | tail -1          # 578+ passing
```

Read the honest numbers aloud in this order: PR-AUC 0.9806 · ROC-AUC
0.9846 · strict gate precision 1.0000 (recall 0.37 — the gate is
conservative by design) · review gate 0.9444 / 0.9125. Then: "both
operating points are reported because the honest number is whichever your
merchants actually run."

## Minute 9–10 · Closing

"One more week: real merchant data, cross-merchant graph for return rings,
outcome webhooks to feed the reflection agent." Same three asks as the
video — panel hears it twice, it lands.

## If the panel takes the keyboard

Hand it over and narrate:
```bash
python scripts/seed_demo_data.py && \
curl -s localhost:8000/v1/return/score -H "X-API-Key: payshield-dev-key-2026" \
  -H "Content-Type: application/json" \
  -d '{"order_id":"ORD_SERIAL_001","user_id":"U_SERIAL_001","merchant_id":"M_FASHION_001","amount":5500,"category":"fashion","payment_method":"UPI","cod_flag":true}' | python -m json.tool
```
Pointer: the HIGH answer is the one where the confirmation box says
"this is a recommendation, not a refusal" — the merchant can ship.

## Timing checkpoints

| 0:00 | 2:00 | 5:00 | 7:00 | 9:00 |
|---|---|---|---|---|
| hook framed | diagram drawn | tests green | numbers up | close |
