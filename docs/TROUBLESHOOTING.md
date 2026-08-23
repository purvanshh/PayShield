# Troubleshooting — Track 2

Symptom → cause → fix. Every fix here is reproducible from a fresh clone.

## "All chargeback responses are PARTIAL with low confidence"

- **Cause:** the audit chain has no `SCORE_DECISION` entry for the txn
  (or the id doesn't match), or the entry exists but the demo was run
  against a different `AUDIT_LOG_DIR`.
- **Fix:** `python scripts/seed_demo_data.py` writes the two demo audit
  entries (`TXN_CLEAN_001`, `TXN_NEW_001`). If seeding a live DB check
  `store/audit_logs/audit_YYYYMMDD.jsonl` exists. Confirm txn id.

## "Every return-risk score is LOW with `default_redis_error` sources"

- **Cause:** Redis unreachable. The engine degrades by design — neutral
  defaults, no crash, no retry.
- **Fix:** `make up`, then re-seed. The provenance tags make this
  diagnosable from the response alone (feature `source` field).

## "Return-risk scores are LOW but the user is a serial returner"

- **Cause:** profiles not seeded, or the Redis key is `return_risk:user:{id}`
  but the request `user_id` differs.
- **Fix:** `python scripts/seed_demo_data.py`, and use the demo ids
  (`U_SERIAL_001` etc. — see `docs/DEMO_DATA.md`).

## "The webhook returns 400 Invalid signature"

- **Cause:** `RAZORPAY_WEBHOOK_SECRET` drift between sender and server.
- **Fix:** use the compose default (`payshield-webhook-dev-secret`) on both
  sides, or set the env identically. Recreate the signature via
  `chargeback.signatures.compute_signature`.

## "Submit returns 403"

- **Cause:** role insufficient (`chargeback:admin` required for `/submit`
  and `auto_submit`).
- **Fix:** register an admin API key (`auth.register_api_key(...)` in a
  script, or use the documented admin role), or generate the draft only.
  Tests use the same gating.

## "Narrative is stiff / not the LLM voice"

- **Cause:** the deterministic fallback — intentionally (no Ollama, or the
  2.0s cap was hit). This is the designed behaviour, not a bug.
- **Fix:** start Ollama (`docker compose up ollama`) and set
  `PAYSHIELD_CHARGEBACK_LLM=true`; the narrative quality score in the
  response tells you which path ran (0.5 = fallback).

## "Benchmark numbers differ from the README"

- **Cause:** different seed/split flags.
- **Fix:** run with defaults (`--users-per-type 100 --orders-per-user 20
  --seed 42`) and report the artifact (`models/return_risk_benchmark_results.json`),
  not the README.

## "`pytest tests/load/...` fails with RecursionError"

- **Cause:** locust monkey-patches on pytest import — by design.
- **Fix:** run via the locust runner (`locust -f tests/load/return_risk_loadfile.py`),
  not pytest. (`tests/load/locustfile.py` is excluded the same way.)

## "Dashboard pages call the API but show nothing"

- **Cause:** Vite proxy / `VITE_API_URL` not pointing at `localhost:8000`,
  or the stack isn't seeded (profile endpoint returns `is_new_user` by
  design for unknown ids).
- **Fix:** dashboard/.env → `VITE_API_URL=http://localhost:8000`, run the
  seeder, then use the demo presets in the UI.

## Quick reference commands

```bash
make test                                          # 578 hermetic tests
python scripts/seed_demo_data.py                   # six curated scenarios
python scripts/benchmark_return_risk.py            # 10k-order benchmark
python scripts/profile_endpoints.py                # in-process latency numbers
pytest tests/chaos -q                              # failure-mode suite
python scripts/security_audit_check.py             # repo posture scan
```
