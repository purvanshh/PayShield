# PayShield v1.0.0 Release Checklist

## Pre-Release

### Code Quality
- [ ] All tests pass: `.venv-test/bin/python -m pytest tests/ -q` (392 passed, 1 skipped)
- [ ] Test coverage ≥ 70% total, ≥ 80% score/ensemble/graph_feature (74%/91%/90%/99%)
- [ ] CHANGELOG updated and reviewed

### Security
- [ ] Dependency scan complete: `make security-scan`
- [ ] No critical vulnerabilities in dependencies
- [ ] Secrets rotated (JWT, API keys, DB passwords)
- [ ] Network policies reviewed
- [ ] Access audit completed
- [ ] TLS certificates valid (not expiring within 30 days)

### Performance
- [ ] p99 latency < 65 ms (`/v1/score`, measured 63.3 ms)
- [ ] L1 rule evaluation p99 < 1 ms (measured 0.27 ms)
- [ ] GNN inference p99 < 3 ms (measured 2.5 ms on CPU)
- [ ] PR-AUC > 2× no-skill baseline (measured 0.195 vs baseline 0.10)

### Documentation
- [ ] API docs generated: `make docs`
- [ ] README updated
- [ ] Getting started guide verified
- [ ] Deployment guide reviewed
- [ ] Troubleshooting guide complete
- [ ] FAQ updated
- [ ] CONTRIBUTING.md up to date

## Release Process

### Versioning
- [ ] Version bumped in `pyproject.toml`
- [ ] Version bumped in `package.json` (dashboard)
- [ ] Git tag created: `git tag v1.0.0`
- [ ] Release branch created: `release/v1.0.0`

### Build
- [ ] Docker images built: `make docker-build`
- [ ] Docker images pushed to registry
- [ ] Images scanned for vulnerabilities
- [ ] Helm chart packaged (if applicable)
- [ ] Release artifacts generated

### Staging Deployment
- [ ] Deployed to staging: `scripts/deploy_k8s.sh staging`
- [ ] Smoke tests pass
- [ ] Integration tests pass
- [ ] Data migration tested (if applicable)
- [ ] Rollback tested

### Production Deployment
- [ ] Deployment window approved
- [ ] Database backup completed
- [ ] Configuration backed up
- [ ] Monitoring alerts configured
- [ ] On-call engineer notified
- [ ] Deployment executed: `scripts/deploy_k8s.sh prod`
- [ ] Health checks pass
- [ ] Traffic gradually shifted (canary)
- [ ] Rollback plan ready

## Post-Release

### Verification
- [ ] All pods healthy
- [ ] Metrics stable (no anomalies)
- [ ] Error rate < 0.1%
- [ ] Latency within SLO
- [ ] Backup jobs running
- [ ] Monitoring dashboards updated

### Communication
- [ ] Release notes published
- [ ] Stakeholders notified
- [ ] Documentation updated
- [ ] Status page updated (if applicable)

### Cleanup
- [ ] Old Docker images pruned
- [ ] Temporary branches deleted
- [ ] Stale resources cleaned up
- [ ] Incident post-mortems reviewed (if any)

## Final Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering Lead | | | |
| DevOps Lead | | | |
| Product Manager | | | |
| Security Team | | | |
| QA Lead | | | |
