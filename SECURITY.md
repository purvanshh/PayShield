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

- **Authentication**: JWT tokens with 24-hour expiry
- **Authorization**: RBAC for all admin endpoints
- **Encryption**: TLS 1.3 in transit, AES-256 at rest
- **Secrets**: SealedSecrets — encrypted in Git, only decryptable by cluster
- **Network**: K8s network policies — zero-trust between pods
- **Audit**: Immutable audit logs for all transactions and admin actions
- **Dependencies**: Automated vulnerability scanning via Dependabot

## Disclosure Policy

We follow coordinated disclosure:
1. Reporter discovers vulnerability
2. Reporter notifies security team privately
3. Team validates and develops fix
4. Fix deployed to production
5. Public disclosure 30 days after fix

## Bug Bounty

We do not currently offer a bug bounty program. Security researchers are recognized in our Hall of Fame for valid reports.
