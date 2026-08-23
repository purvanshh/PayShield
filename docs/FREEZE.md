# Freeze Record — Track 2 Codebase Frozen

**Frozen at:** `feature/track2-risk-manager` @ 2026-08-22 · **Freeze tag:**
`v1.2.0-track2-final` (annotated, same commit as the release tag after this
record).

## Verification at freeze time

| Gate | Command | Result |
|---|---|---|
| Tests | `pytest tests/ -q` | **573 passed, 1 skipped** (hermetic) |
| Types | `mypy chargeback/ return_risk/ --strict --follow-imports=skip` | 0 errors, 13 files |
| Lint | `ruff check` on all track-2 dirs | clean (pre-existing repo-wide B008 `Depends` convention excepted; matches `api/routes/score.py`) |
| Security | `bandit -r chargeback return_risk` | 0 findings (4 documented rails) |
| Secrets | `scripts/security_audit_check.py` | 0 HIGH, 488 files scanned |
| Compliance | 3 checkers, compose env | PCI 90/100 · RBI 83/100 (passing) · EU 100/100 |
| Bench | `scripts/benchmark_return_risk.py` (defaults) | PR-AUC 0.9806 · P 1.0000/HIGH · P 0.9444 R 0.9125/MEDIUM+ |
| Demo seed | `scripts/seed_demo_data.py` + scenarios | six verified scenarios (`docs/DEMO_DATA.md`) |

## Freeze rules

1. **No new features.** Anything not in the tree stays out until after the
   panel interview.
2. **Bugs discovered during panel prep:** a `fix:` commit only — on this
   branch, rebased, with a test; never a silent data re-spin.
3. **The implementation plan files** (Kimi Phases 1–50 markdown) are
   intentionally untracked; they are working notes, not repo assets.
4. **Manual items are not frozen** — repo/video/form actions in
   `docs/SUBMISSION_CHECKLIST.md` are yours to run; code is not touched by
   them.

## If something breaks on panel day

- API down → `make up` then re-seed; the stack is compose-scripted.
- Redis down → scores degrade to neutral defaults *by design* (chaos-tested);
  say so on camera.
- Ollama down → deterministic narrative (by design); the rebuttal is still
  correct.

This is the stable state. Confidence comes from it.
