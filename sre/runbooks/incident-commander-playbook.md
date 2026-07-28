# Incident Commander Playbook

## Severity Levels

| Level | Description | Response | Communication |
|-------|-------------|----------|---------------|
| SEV1 | Revenue-impacting, data loss | All-hands war room | Status page every 15 min |
| SEV2 | Degraded service, workaround | On-call + eng lead | Internal update every 30 min |
| SEV3 | Minor degradation | Ticket next business day | None required |

## Commander Responsibilities

1. **Declare incident** — Set severity, assemble response team
2. **Coordinate** — Assign roles (comms, ops, root cause)
3. **Communicate** — Status updates, stakeholder notifications
4. **Decide** — Mitigate, rollback, or continue
5. **Resolve** — Confirm fix, monitor for stability
6. **Learn** — Schedule post-mortem within 24 hours

## Timeline

```
T+0:    Incident detected (alert or user report)
T+5:    Commander assigned, severity declared
T+15:   Initial assessment complete
T+30:   Mitigation in progress
T+60:   Service restored or workaround deployed
T+24h:  Post-mortem scheduled
```

## Communication Template

```
SUBJECT: [SEV1] PayShield — [brief description]
CURRENT STATUS: [detecting | mitigating | monitoring | resolved]
SCOPE: [what systems/users are affected]
TIMELINE: [key events so far]
ACTION: [what is being done]
NEXT UPDATE: [time]
```
