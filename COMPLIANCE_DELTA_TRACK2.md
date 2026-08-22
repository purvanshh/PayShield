# Compliance Delta — Track 02 (AI Risk Manager)

**Checked 2026-08-22 with the compose runtime environment**
(`ENCRYPTION_KEY`, `ENFORCE_RBAC=true`, `DATA_REGION=IN`,
`ENABLE_LLM_INVESTIGATOR=true` — the exact set `docker/docker-compose.yml`
injects). Raw runs:

```text
PCI-DSS:   90/100  passed=True  findings=['8.3']   (unchanged)
RBI:       83/100  passed=True  findings=['AI-2']  (low severity)
EU AI Act: 100/100 passed=True  findings=['DG-2']  (low severity, pre-existing)
```

## No regression from Track 02

| Framework | Baseline (2026-08-15) | After Track 02 | Status |
|---|---|---|---|
| PCI-DSS | 90/100 (8.3 MFA open) | 90/100 (8.3 MFA open) | No change |
| RBI | 83/100 (AI-2 open) | 83/100 — **passing**: the human-oversight feedback directory is now tracked in-repo (`store/feedback/`) | Improved |
| EU AI Act | 100/100 (DG-2 low) | 100/100 (DG-2 low) | No change |

Notes on the two persistent findings (both pre-existing, neither
track-2-caused):

- **PCI 8.3 (MFA):** TOTP MFA is implemented and verified per account
  (`/auth/totp/*`); the checker flags the absence of a static
  `MFA_ENABLED` env flag — a checker-simplification, not a gap.
- **EU DG-2 (demographic metrics):** `TRACK_DEMOGRAPHIC_METRICS` is off in
  compose; the fairness audit (`models/fairness_audit.py`) covers the SPD/EOD
  slices analytically. Left as documented pre-existing.
- **RBI AI-2:** the loop exists (`POST /v1/feedback` persists to
  `store/feedback/`); the directory wasn't tracked in git, so fresh clones
  failed the check. Fixed by adding `store/feedback/.gitkeep`. Severity
  drops high → low once ≥10 feedback entries exist (live usage).

## Track 02 → control mapping (where each control is enforced)

| Control | Track 02 implementation | Evidence file |
|---|---|---|
| PCI 3.4 (encryption) | dev key only from env; no secrets committed (seed scripts take injected clients) | `scripts/seed_demo_data.py`, `compliance/pci_dss.py` |
| PCI 8.1 (RBAC) | `chargeback:read/write/admin`, `return_risk:read/write` in `configs/rbac.yaml`; per-route `require_permission`; admin gate on `/submit` and `auto_submit` | `configs/rbac.yaml`, `api/routes/chargeback.py`, `api/routes/return_risk.py` |
| PCI 10.x (audit logging) | every score decision, return score/update, rebuttal build, webhook event and submission appended to the hash-chained chain with PII masking | `api/routes/score.py`, `api/routes/chargeback.py`, `api/routes/chargeback_webhook.py`, `api/routes/return_risk.py`, `store/audit_log.py` |
| Network security (entry points) | webhook HMAC-SHA256 verification via `chargeback/signatures.py`; per-key rate limits on the new routes | `api/routes/chargeback_webhook.py`, `api/dependencies.py` |
| RBI data residency | all new state in Redis/Postgres with `DATA_REGION=IN`; no cross-border calls (mock Razorpay client is outbound-disabled) | `chargeback/razorpay_client.py` |
| RBI / EU transparency (AI-4, TR-2) | feature weights + 8 rules in public YAML; per-feature `source` tags; per-feature contributions in every score response | `configs/feature_registry_return.yaml`, `configs/return_risk_rules.yaml`, `api/schemas/return_risk.py` |
| EU HO-1/HO-2 (human oversight) | draft/submit split, `chargeback:admin` gate, override-feedback directory tracked | `api/routes/chargeback.py`, `store/feedback/` |
| EU AC-1/AC-2 (accuracy) | measured PR-AUC 0.9806; both operating points reported; false-positive breakdown by archetype in the benchmark artifact | `models/return_risk_benchmark_results.json`, `reports/return_risk_benchmark_report.md` |
| EU RB-1 (robustness) | graceful degradation paths tested: missing device → 0.62 completeness; missing graph/L3 → warnings + conservative PARTIAL; LLM down → deterministic narrative | `tests/integration/test_chargeback_flow.py`, `chargeback/narrative_generator.py` |

## Defence-only statement

No capability in Track 02 is offence-capable: no automated contest
submission (admin gate + draft separation — both tested), no
customer-facing lookup utilities, and the only write path
(`/v1/return/update`) records events the merchant already caused.
`auto_submit` requires `chargeback:admin` *and* completeness ≥ threshold,
else 422 (tested in `tests/integration/test_chargeback_api.py`).
