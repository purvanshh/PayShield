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
- [ ] Unit tests added for new functionality
- [ ] Integration tests updated if API changes
- [ ] Documentation updated if public API changes
