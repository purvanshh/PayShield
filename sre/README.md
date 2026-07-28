# Site Reliability Engineering

## Structure

```
sre/
├── slos/                          # Service Level Objectives
│   ├── fraud-scoring-slo.md       # Core scoring SLOs
│   ├── investigation-slo.md       # Investigation pipeline SLOs
│   └── dashboard-slo.md           # Dashboard SLOs
├── error-budgets/
│   └── q3-2026-error-budget.md    # Error budget policy
├── runbooks/
│   ├── on-call-rotation.md        # On-call schedule & responsibilities
│   ├── incident-commander-playbook.md  # Incident management
│   ├── post-mortem-template.md    # Post-incident analysis
│   └── escalation-policy.md       # Escalation hierarchy
├── chaos/
│   ├── experiments/               # LitmusChaos experiment definitions
│   │   ├── api-pod-failure.yaml
│   │   ├── redis-network-partition.yaml
│   │   ├── postgres-high-latency.yaml
│   │   ├── neo4j-node-drain.yaml
│   │   └── ollama-resource-exhaustion.yaml
│   └── litmus-chaos-setup.md      # Installation & usage
└── README.md
```

## Quick Links

- [Fraud Scoring SLO](slos/fraud-scoring-slo.md)
- [Incident Commander Playbook](runbooks/incident-commander-playbook.md)
- [Chaos Experiments](chaos/experiments/api-pod-failure.yaml)
- [Error Budget Policy](error-budgets/q3-2026-error-budget.md)
