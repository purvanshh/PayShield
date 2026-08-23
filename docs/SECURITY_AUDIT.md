# Security Audit — Track 2 (2026-08-22)

Ran with the reproducible runner (`scripts/security_audit_check.py`),
bandit on the risk modules and safety against the pinned range set.
Everything verifiable from the tree is verified; everything that needs a
stack is marked.

## Runner output summary

```json
{
  "files_scanned": 488,
  "high_findings": [],
  "low_findings": ["password-ish string: .env.example", "auth.py", "pci_dss.py", "redis_bridge.py", "connection_pool.py", "neo4j_client.py", "sync_redis.py"],
  "gitignore": {"covers env": true, "covers audit logs": true, "covers node_modules": true,
                "tracked_env_files": [".env.example", "dashboard/.env.example"]}
}
```

The "password-ish" hits are `os.getenv("...PASSWORD", "")` and
redis-bridge wiring — references, not secrets. `.env.example` is a
template (documented values placeholder). No AWS/private-key/live-key
patterns; 0 HIGH.

## Dependency scan

`safety check -r requirements.txt` → **0 vulnerabilities reported**;
65 ignored because many ranges are unpinned (floating `>=`).
Actionable follow-ups found and applied:
- `requests>=2.32.0` (advisories on <2.32)
- `aiohttp>=3.10.6` (CVE-2024-30251 & friends <3.10.5)
- `PyJWT>=2.10.1` (CVE-2024-53861 & friends <2.10.1)

## Bandit (already part of the quality gate)

`bandit -r chargeback return_risk` → **0 findings**; 4 documented `nosec`
rails (whitelisted-scope rules evaluator, deliberate swallow paths,
fixture contract asserts).

## Control matrix

| Control | Status | Evidence |
|---|---|---|
| AuthN: API key + JWT + TOTP | enforced | `api/auth.py`, `/auth/*` tests |
| AuthZ: least privilege | enforced | `configs/rbac.yaml` (write ≠ admin), 403 tests in `test_chargeback_api.py` |
| Rate limits | enforced | per-IP 200/min, per-key 1000/hr; 429 tests in `test_security_api.py` |
| Webhook HMAC (SHA-256, constant-time) | enforced | `chargeback/signatures.py`, `test_webhook.py` |
| Injection (SQL/path/eval) | safe by construction | ORM-only data layer; no user strings reach SQL (reason_code is opaque, see `test_security_edges.py`); ONE evaluated surface is the whitelisted rule engine (documented, bandit-annotated) |
| File upload surface | none exposed | `razorpay_client.upload_evidence_file` is a client-side helper; no public endpoint accepts uploads |
| PII in logs | masked pre-hash | `store/audit_log.py` (documented masking test) |
| Secrets in repo | none HIGH | runner scan; env-based config |
| TLS/mTLS, key rotation | out of scope | infra-level, documented as production follow-up |
| Signed/audited submissions | enforced | admin gate + audit chain + idempotent draft cache |

## Pen-test scenarios (as run)

1. **SQLi via `reason_code`** → payloads like `10.4; DROP TABLE users;--`
   and `' OR '1'='1'` are treated as opaque strings (document + rules table
   keys only); round-trip serialization asserted — no SQL touched.
2. **Path traversal via upload** → no public upload endpoint exists; the
   client helper opens paths the *operator* supplies, not HTTP input.
3. **RBAC bypass** → 403 on `/submit` and `auto_submit` without
   `chargeback:admin` (integration suite); the attempt is audited by the
   route's audit append.
4. **Rate-limit exhaustion** → 429 with `Retry-After` (existing security
   tests, per-key window).
5. **Prompt injection into narrative** → malicious descriptions are quoted
   evidence text; Jinja autoescape is off only for the plain-text prompt
   by design, and the deterministic fallback is invoked on LLM failure —
   the verdict path never depends on the narrative (edge tests assert).

## Verdict & remediation

- **No HIGH findings.**
- Applied: dependency minimums bumped (3 pins above).
- Open (accepted, documented): infra-level controls (TLS 1.3, mTLS, key
  rotation, ASV scan) belong to deployment, not code; noted in
  `COMPLIANCE_DELTA_TRACK2.md`'s remaining-findings section.
- Recommendation: run `python scripts/security_audit_check.py` in CI at
  tag time (add to a post-merge workflow when the repo is made public).
