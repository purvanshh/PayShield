# Performance Optimization — Track 2 Hot Paths

**Measured 2026-08-22, `scripts/profile_endpoints.py --iterations 300`
(environment: **in-process**, no ASGI/network hop — the numbers below are
the pipeline arithmetic; API-visible latency adds the transport/Redis
network leg, and the live-stack `latency_ms` field is the honest end-to-end
number per request).**

## Measured (in-process pipeline, 300 iterations)

| Path | p50 | p95 | p99 |
|---|---|---|---|
| Return-risk score (serial-returner profile, full pipeline) | 0.10 ms | 0.13 ms | 0.32 ms |
| Chargeback rebuild (audit read → collect → build → fallback narrative) | 0.05 ms | 0.06 ms | 0.12 ms |

## What was already concurrent — and verified

- `ReturnRiskFeatureEngine.extract_features` fetches user and merchant
  features with `asyncio.gather` (1 round-trip instead of 2). Verified in
  the code path and kept.
- Redis connection pool default is `max_connections=50` with
  `socket_timeout=2.0` (`store/connection_pool.py`) — the loader
  suggestion of 10→50 is already the shipped default; nothing to change.

## Optimizations applied this pass

1. **LLM narrative timeout cap (real tail-latency fix).**
   Before: the narrative awaited `OllamaClient.generate` with Ollama's own
   300 s client timeout — a stalled model could hold the rebuttal endpoint
   hostage. After: `NarrativeGenerator(llm_timeout=2.0)` wraps the await in
   `asyncio.wait_for`; on timeout the deterministic fallback narrative is
   returned and the failure is logged. The 30-second-user-hostile scenario
   is pinned as a chaos test (`TestLLMTimeoutCap`) — elapsed < 2 s, rebuttal
   still produced.

2. **Best-effort drift sampling off the hot path.**
   The return-risk score route records PSI samples after the response is
   computed; failures are swallowed (never 500) and the sampling is one
   pipeline call with 30-day prune.

## Known tail costs (honest)

- **Audit read-back is O(entries)** — `AuditLogReader.get_transaction`
  scans the JSONL chain. Bounded per file (5,000 entries, rotated) and
  acceptable at merchant scale; a per-txn entry index is the documented
  next step if read-back rates rise.
- **The 2.0 s narrative cap is the worst-case rebuttal latency** — by
  design, only the *presentation* stream caps; the verdict (response type
  + payload) is available before the LLM is consulted.
- Live-stack end-to-end numbers (p50/p95 over HTTP, incl. Redis network
  hops) require the load harness run — see `docs/LOAD_TESTING.md`; do not
  cite the in-process numbers as API latency.

## Artifacts

- `reports/perf_optimization.json` — this run's raw numbers.
- `tests/chaos/test_chaos_track2.py::TestLLMTimeoutCap` — the guard test.
