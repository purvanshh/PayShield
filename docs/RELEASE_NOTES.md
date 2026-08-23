# Release Notes — PayShield v1.2.0 (Track 02: AI Risk Manager)

**Date:** 2026-08-22 · **Tag:** `v1.2.0-track2` · **Branch:**
`feature/track2-risk-manager`

## Chargeback Evidence Responder

- Rebuttal assembly from point-in-time evidence — the collector reads the
  tamper-evident audit chain and Redis mirrors, never re-analyses.
- Rule-based ACCEPT/REJECT/PARTIAL with network-aware urgency
  (UPI 7d · Visa/MC 30d · Amex 20d · RuPay 15d).
- LLM narrative with a 2.0s deadline cap and a deterministic fallback
  (jury-proof when Ollama is down; pinned by a chaos test).
- Razorpay payload built in one method; mock-mode client with realistic
  fixtures (`open → under_review → won/lost`).
- Signed webhook (`/webhooks/razorpay/chargeback`) that caches
  auto-rebuttals; submission and auto-submit gated by `chargeback:admin`
  (human-in-the-loop, tested).

## Return-Risk Scorer

- 7 weighted features with per-feature `value · weight · contribution ·
  source` in every response; weights public YAML.
- 8 config-driven rules (whitelisted-scope evaluation, per-rule graceful
  degradation, reload without deploy).
- Capped rule adjustments so stacked risk lands in the right tier while
  the weight signal stays primary.
- Honest confidence, neutral (never zero) defaults for new users, and
  provenance-aware degradation tags (`default_redis_error`) when the
  store is down.

## Measured (synthetic, seed 42, 10k orders, chronological hold-out)

| Metric | Value |
|---|---|
| PR-AUC | **0.9806** |
| ROC-AUC | 0.9846 |
| Precision @ HIGH cut (prepaid gate) | 1.0000 · recall 0.3675 |
| Precision @ MEDIUM+ cut (flag for review) | 0.9444 · recall 0.9125 · F1 0.9282 |

Both operating points reported at the shipped tier boundaries.

## Feedback loops & ops

- Nightly reflection: tier precision, per-user-type misses, chargeback
  outcome matrix, auto-recommendations (threshold/strategy/retrain).
- Champion/challenger weight experiments (sha256-stable merchant
  bucketing) with admin-gated create/evaluate endpoints.
- PSI drift monitor for the six return-risk features
  (`/admin/drift/return-risk`), sampled best-effort off the hot path.
- Prometheus counters/histograms for both new surfaces.

## Quality

- 580 tests (hermetic), 76.4% suite coverage · 91.1% track-2 modules
- strict mypy on all 13 logic modules · bandit 0 findings (4 documented
  rails) · comprehension: chaos suite (Redis/LLM/Razorpay failures),
  grand E2E pipeline, locust workload file
- Compliance in the compose runtime env: PCI-DSS 90/100, RBI 83/100
  (passing), EU AI Act 100/100

## Notes

- The payload contract is documented against Razorpay's disputes API with
  an explicit "verify against a real sandbox key" gap — mock mode is a
  contract tool, not a substitute for a live check.
- A load run against the live stack is the remaining artifact before
  citing end-to-end API latency; the harness is in `tests/load/`.
