# Deep-Dive Video Outline (optional, ~2 minutes)

A short bonus video for judges who want depth after the 5-minute pitch.
It answers the question the main video can't: "show me how it works."

## Segment plan

| Time | Segment | Show on screen | Say |
|---|---|---|---|
| 0:00–0:45 | Code walkthrough | `chargeback/rebuttal_builder.py` — the build pipeline (evidence → response type → narrative → payload) with the `RULE_BOOST` call-site and `_build_razorpay_payload` highlighted by cursor | "seven steps, all deterministic except the narrative" |
| 0:45–1:15 | Evidence reconstruction | `chargeback/evidence_collector.py` — the audit-chain read and the `ud:{user_id}` device lookup | "we never re-analyse; judge it by the point-in-time record" |
| 1:15–1:35 | Tests | `pytest tests/unit/chargeback tests/unit/return_risk tests/integration -q` tail (537 passed line) | "hermetic — no Redis, no Neo4j, no Ollama needed" |
| 1:35–1:50 | Types + lint | `mypy chargeback return_risk --strict --follow-imports=skip` then `ruff check chargeback return_risk` | "0 errors on all thirteen business-logic files" |
| 1:50–2:00 | Wrap | repo tree, `docs/DESIGN_DECISIONS.md` open | link the two deeper docs |

## Production notes

- Same terminal font rules as the main video (18pt+, dark theme).
- Pre-run every command once; paste, don't type.
- Key the chapters at 0:00 / 0:45 / 1:15 / 1:35 / 1:50.
- Export 1080p30 H.264; upload unlisted; add the link under "Deep dive" in
  the README beside the main video link.

## Honesty guard

- Run the commands live in the recording — screenshots of stale runs are
  not acceptable in this repo's own standard.
- If a command fails on camera because of environment drift, say the
  expected line and fix it live — that is the correct edit, not a cut.
