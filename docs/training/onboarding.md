# Developer Onboarding Guide

## First Week

### Day 1: Environment Setup

- [ ] Clone repository and install dependencies
- [ ] Run `make dev` to start local environment
- [ ] Complete [Getting Started Guide](../guides/getting-started.md)
- [ ] Verify `curl localhost:8000/health` returns OK
- [ ] Run test suite: `make test`

### Day 2: Core Concepts

- [ ] Read [Architecture Overview](../architecture/overview.md)
- [ ] Review [Track 2 Architecture](../TRACK2_ARCHITECTURE.md)
- [ ] Read [API Reference](../API_REFERENCE.md)
- [ ] Execute a test transaction: `python scripts/quick_test.py`
- [ ] Explore the codebase structure

### Day 3: Development Workflow

- [ ] Create a feature branch from `develop`
- [ ] Implement a small change (e.g., add a rule)
- [ ] Write tests for the change
- [ ] Submit a pull request
- [ ] Review a colleague's PR

### Day 4: Operations

- [ ] Review [Track 2 Architecture](../TRACK2_ARCHITECTURE.md)
- [ ] Practice deploy to dev environment
- [ ] Review [Track 2 Architecture](../TRACK2_ARCHITECTURE.md) for observability
- [ ] Simulate incident using runbooks

### Day 5: Advanced Topics

- [ ] Review [Agent System](../architecture/agents.md)
- [ ] Understand Celery task workflow
- [ ] Review LLM investigator configuration
- [ ] Shadow on-call engineer

## Key Resources

### Documentation
- `docs/` - Complete documentation suite
- `CONTRIBUTING.md` - Contribution guidelines
- `Makefile` - Common development commands

### Communication
- **Slack**: #payshield-dev (development), #payshield-alerts (incidents)
- **Email**: dev@payshield.io
- **Standup**: Daily 10:00 AM
- **Sprint Planning**: Monday 11:00 AM

### Tools & Access

| Tool | URL | Purpose |
|------|-----|---------|
| GitHub | github.com/your-org/payshield | Code, issues, PRs |
| Grafana | grafana.payshield.io | Dashboards |
| Sentry | sentry.io/org/payshield | Error tracking |
| ArgoCD | argocd.payshield.io | Deployment management |
| Jira | jira.payshield.io | Task tracking |
