# Contributing to PayShield

## Branch Naming
- `feature/<short-description>` — New features
- `fix/<short-description>` — Bug fixes
- `phase/<number>` — Implementation phases

## Commit Message Format
```
<phase/tag>: <short description>

<optional body with details>
```

## Pre-commit Requirements
Before committing, ensure:
1. `make pre-commit` passes (runs ruff, mypy, bandit, and security checks)
2. `make test-unit` passes
3. No secrets, private keys, or credentials are included
4. Files larger than 500KB are handled via Git LFS or `.gitignore`

## PR Checklist
- [ ] Code follows project style (run `make format`)
- [ ] Type checks pass (run `make typecheck`)
- [ ] Tests pass (run `make test`)
- [ ] Linting passes (run `make lint`)
- [ ] Unit tests added for new functionality
- [ ] Integration tests updated if API changes
- [ ] Documentation updated if public API changes
- [ ] Security implications reviewed
- [ ] Compliance impact considered (PCI-DSS / RBI / EU AI Act)
- [ ] Updated `TECHNICAL_DEBT_REGISTER.md` if introducing debt

## Model Retraining
- Use `make retrain` for the canonical benchmark-on-gate-on-promote flow (config in `configs/train_config_retrain.yaml`, gate epsilon 0.005 PR-AUC via `scripts/check_improvement.py`).
- Candidates must beat the currently promoted registry model to be registered; use `make retrain-gate` to evaluate an existing benchmark JSON without promoting.
- The weekly run is automated in `.github/workflows/retrain.yml`; never promote a model over a manual run without review.

## Code Review Process
- All PRs require at least 1 approval
- Security-sensitive changes require security team review
- ML model changes require ML engineer review
- Infrastructure changes require DevOps/SRE review
