# PayShield Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in PayShield, please:

1. **Do not** open a public GitHub issue
2. Email: security@payshield.io
3. Include: description, steps to reproduce, affected versions, potential impact

We aim to:
- Acknowledge receipt within 24 hours
- Provide initial assessment within 72 hours
- Release fix within 14 days (critical) or 30 days (medium/low)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x | Yes |
| < 1.0 | No |

## Security Practices

- **Authentication**: API keys (`x-api-key`) + JWT tokens with configurable expiry
- **Authorization**: RBAC enforced on all admin endpoints (`ENFORCE_RBAC=true` in compose; roles in `configs/rbac.yaml`)
- **Encryption**: TLS 1.3 in transit, AES-256 at rest (`ENCRYPTION_KEY` env, PCI-DSS 3.4)
- **Audit**: Tamper-evident audit log — append-only JSONL with SHA-256 hash chaining and PII masking (PAN, UPI IDs, device fingerprints) written on every scoring decision (`store/audit_log.py`, PCI-DSS 10.1)
- **Secrets**: SealedSecrets in Kubernetes — encrypted in Git, only decryptable by cluster; dev-only defaults in `.env.example` must be rotated in production
- **Network**: K8s network policies — zero-trust between pods
- **Dependencies**: Automated vulnerability scanning via Dependabot

## Known Gaps

| Area | Status |
|------|--------|
| MFA for admin accounts (PCI-DSS 8.3) | Deferred — TOTP login is the next hardening item |
| Dashboard auth tokens in localStorage (TD-003) | Pending — httpOnly cookies planned |

## Disclosure Policy

We follow coordinated disclosure:
1. Reporter discovers vulnerability
2. Reporter notifies security team privately
3. Team validates and develops fix
4. Fix deployed to production
5. Public disclosure 30 days after fix

## Bug Bounty

We do not currently offer a bug bounty program. Security researchers are recognized in our Hall of Fame for valid reports.
