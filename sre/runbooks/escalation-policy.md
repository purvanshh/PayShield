# Escalation Policy

## Contact Hierarchy

| Level | Role | Contact Method | Response SLO |
|-------|------|----------------|-------------|
| 1 | Primary On-Call | PagerDuty | 5 min |
| 2 | Secondary On-Call | PagerDuty | 10 min |
| 3 | Engineering Lead | Phone | 15 min |
| 4 | VP Engineering | Phone | 20 min |
| 5 | CTO | Phone | 30 min |

## When to Escalate

- **SEV1** immediate escalation to Level 3
- **No response** from primary after 5 min
- **Incident exceeds 30 min** without resolution
- **Multiple simultaneous incidents** requiring coordination
- **Customer impact** affecting > 1% of users

## Communication Channels

| Channel | Purpose |
|---------|---------|
| #payshield-alerts (Slack) | Automated alerts |
| #payshield-incidents (Slack) | Incident coordination |
| Phone bridge | War room during SEV1 |
| Status page | External communication |
