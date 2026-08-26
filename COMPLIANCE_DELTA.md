# Compliance — Out of Scope (PoC)

> **Disclaimer:** No certifications have been sought or obtained for this
> Proof-of-Concept. PCI-DSS, RBI and EU AI Act certification are **out of
> scope**; the audit-chain infrastructure (`store/audit_log.py`) is designed to
> *support* future certification, not to claim it.

Earlier versions of this repo carried programmatic self-assessment scores
(PCI-DSS 90/100, RBI 100/100, EU AI Act 100/100) produced by
`compliance/*ComplianceChecker` modules. Those were **self-assessments, not
third-party audits**, and the checker modules have since been removed from the
repo. The historical scores should not be read as certifications.

## What the codebase supports today (future-work scaffolding)

| Capability | Where | Relevance to future certification |
|---|---|---|
| Tamper-evident audit log | `store/audit_log.py` | Append-only JSONL with SHA-256 hash chaining, genesis-hash verification, PII masking at write — the substrate for PCI-DSS 10.x / RBI retention |
| RBAC on admin routes | `configs/rbac.yaml` + `api/rbac.py` | Every admin route gated by `require_permission(...)` |
| TOTP MFA for admin | `api/routes/auth.py` | RFC 6238 (SHA-1, 30s step, pure stdlib) — PCI-DSS 8.3-shaped |
| JWT refresh rotation | `api/routes/auth.py` | 7-day sliding window, token-jti revocation |
| Per-key / per-user rate limiting | `api/security.py` | 1000 req/hr Redis incr+TTL |
| CORS restriction | `api/main.py` | Env-driven `FRONTEND_URL`, no wildcard |
| Data region marker | `docker/docker-compose.yml` | `DATA_REGION=IN` |

## How to verify the audit chain

```bash
docker compose -f docker/docker-compose.yml up -d
python scripts/seed_demo_data.py
# drive a few /v1/return/score and /v1/return/update calls, then:
docker compose -f docker/docker-compose.yml exec api python -c \
  "from store.audit_log import audit_logger; print(audit_logger.verify_chain())"
```

See the honest engineering ledger — including the "AUC > 0.92" correction and
the PSI-estimator fix — in [`MISTAKES_AND_LEARNINGS.md`](MISTAKES_AND_LEARNINGS.md)
and [`docs/THREE_HARD_BUGS.md`](docs/THREE_HARD_BUGS.md).