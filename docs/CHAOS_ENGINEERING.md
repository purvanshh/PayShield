# Chaos Engineering — Track 2 Failure Modes

Three infrastructure-failure experiments for the risk suite, all passing,
all hermetic (`pytest tests/chaos` — no services needed). Run:

```bash
pytest tests/chaos/test_chaos_track2.py -v
```

## Experiment 1 — Redis outage during return-risk scoring

**Injection:** every call on the store raises `ConnectionError`
(BrokenRedis double).

**Expected — observed:**
- `extract_features` degrades to neutral defaults instead of raising
- provenance tags switch to `default_redis_error` (visible in the API
  `feature_breakdown` — the merchant sees *why* the score is flat)
- no retry loop, no exception; the scorer returns a bounded score
- with a fully flat profile, no rules fire (evaluator stays sane)

**Code:** `_safe_redis()` in `return_risk/feature_engine.py` is the single
degradation point — every store read flows through it. It also covers the
`update_user_profile` write path, which is best-effort by design (the
profile refresh can be dropped; the score response cannot).

## Experiment 2 — LLM outage during chargeback narrative

**Injection:** `OllamaClient.generate` raises `TimeoutError`.

**Expected — observed:**
- the rebuttal is still produced end-to-end
- the narrative comes from the deterministic fallback
  (`quality_score` 0.5, evidence-derived facts — never empty, never fake)
- confidence/completeness math is unaffected (the narrative is a
  presentation layer; the verdict comes from evidence)

**Code:** `NarrativeGenerator.generate()` — LLM call plus parse, both
guarded; everything above the store goes through the same path, so an
Ollama restart mid-demo degrades to a working fallback rather than a blank
screen.

## Experiment 3 — Razorpay submission timeout

**Injection:** transport raises `httpx.ReadTimeout` /
`httpx.ConnectTimeout`.

**Expected — observed:**
- `RazorpayAPIError` with `status_code 503` surfaces immediately (no
  waiting out the client timeout in the API layer — the route maps it to
  502)
- the error body carries `status_code` and the mirrored response so
  operators can see exactly which call failed
- nothing is retried automatically; the draft stays cached
  (`chargeback:rebuttal:{dispute_id}`), so a re-submit after recovery is
  the same payload — no duplicate-contest risk

**Code:** `RazorpayClient._request()` — the single network path,
transport-failure mapped, `_handle()` mapping 4xx/5xx bodies.

## What this proves

- The checkout-time scorer survives a store outage without a 500.
- The responder works with or without the LLM.
- Submissions fail closed, fast, and idempotently.
- Each behaviour is pinned by a deterministic test — not a live-DB restart
  ritual.
