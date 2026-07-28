# PayShield v1.0.0

## Release Date
2026-07-28

## Release Artifacts

| Artifact | Location |
|----------|----------|
| Release Checklist | `RELEASE_CHECKLIST.md` |
| Handoff Document | `HANDOFF_DOCUMENT.md` |
| Release Check Report | `releases/v1.0.0/release-check-report.json` |
| Docker Images | `payshield/api:1.0.0`, `payshield/celery-worker:1.0.0` |
| K8s Manifests | `k8s/overlays/prod/` |
| Documentation | `docs/` |

## Changelog

See [changelog](../../docs/reference/changelog.md) for full details.

## Quick Start

```bash
# Verify release
python scripts/final_release_check.py

# Deploy to production
./scripts/deploy_k8s.sh prod
```
