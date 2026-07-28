# Frequently Asked Questions

## General

### What is PayShield?
PayShield is an enterprise fraud detection system that uses ensemble machine learning, LLM-powered investigation, and multi-agent orchestration to detect fraudulent transactions in real-time.

### How does PayShield compare to traditional rules-based systems?
PayShield combines ML models (catching novel patterns) with traditional rules (known fraud patterns), achieving 40% higher detection rate with 60% fewer false positives.

### Can PayShield run on-premise?
Yes. PayShield is containerized and can run on any Kubernetes cluster, including on-premise deployments.

## Technical

### What ML models does PayShield use?
5 base models (XGBoost, LightGBM, CatBoost, RandomForest, MLP) plus a Gradient Boosting meta-learner.

### How long does a single transaction take to score?
Typically 30-100ms for the ensemble path. Investigations add 500ms-5s for LLM + agents.

### What happens if the LLM is unavailable?
PayShield degrades gracefully. If LLM is unavailable, the system uses only the ensemble + rule-based detection, falling back from "investigate" to "manual review" status.

### How is data privacy handled?
- All PII is encrypted at rest (AES-256)
- Network policies restrict data access
- LLM calls can be configured to strip PII
- On-premise deployment option available

### How does PayShield handle model drift?
Automatic drift detection monitors feature distributions and model confidence. When drift is detected, retraining is triggered automatically.

## Operations

### What is the backup strategy?
PostgreSQL: every 6 hours, retained 30 days. Redis: daily, retained 7 days. Config: daily, retained 90 days. All backups are stored in S3.

### What is the disaster recovery RTO/RPO?
RTO: 15 minutes, RPO: 1 hour for critical systems.

### How do I scale PayShield?
Horizontal scaling via HPA (auto-scales based on CPU/memory). Celery workers can be scaled independently. PostgreSQL read replicas for analytics workloads.

### What monitoring is built-in?
Prometheus metrics, structured logging, Sentry error tracking, Grafana dashboards, and alertmanager with PagerDuty/Slack integration.

## Development

### How do I add a new model?
Create model class in `ml/models/`, register in ensemble, add training routine, write tests.

### How do I contribute?
See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines. All contributions go through PR review process.

### What testing coverage is required?
80%+ code coverage. All new features require unit tests, integration tests, and E2E tests for critical paths.

### How do I debug a production issue?
1. Check Grafana dashboards for anomalies
2. Search logs in Loki/Splunk
3. Review Sentry for error traces
4. Follow troubleshooting runbook in `docs/operations/troubleshooting.md`

## Security

### How are secrets managed?
SealedSecrets for Kubernetes. Secrets are encrypted and stored in Git. Only the cluster can decrypt them.

### Is TLS enforced?
Yes. TLS termination at ingress level. Internal service-to-service communication can optionally use mTLS.

### How is access controlled?
JWT-based authentication for API. Kubernetes RBAC for cluster access. VPN required for production cluster access.

### Are there compliance certifications?
SOC 2 Type II in progress. GDPR compliant by design. PCI DSS compliant deployment option available.

## Pricing

### What is the pricing model?
Contact sales@payshield.io for pricing. Self-hosted (free, MIT license) and Enterprise (managed, with SLA) options available.

### Estimated infrastructure costs?
Development: ~$80/month, Staging: ~$200/month, Production: ~$874/month (optimized). See [Cost Analysis](../../cost/COST_ANALYSIS.md) for details.
