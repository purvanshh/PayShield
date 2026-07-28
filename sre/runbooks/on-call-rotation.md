# On-Call Rotation

## Schedule

- **Rotation Period:** 1 week (Monday 10:00 → Monday 10:00)
- **Primary:** Single engineer, full-time focus
- **Secondary:** Backup engineer, available within 5 minutes
- **Handoff:** 30-minute meeting every Monday

## Responsibilities

- Monitor alerts and dashboards
- Respond to incidents within SLO
- Triage and escalate as needed
- Document all incidents in `incidents/`
- Update runbooks with learnings

## Escalation

| Time | Action |
|------|--------|
| 0 min | Alert fires |
| 5 min | No response → secondary paged |
| 10 min | No response → engineering manager |
| 15 min | No response → CTO |

## Access

- SSH access to production cluster
- Admin API credentials (break-glass only)
- Direct line to engineering lead
- PagerDuty/Opsgenie for alert routing
