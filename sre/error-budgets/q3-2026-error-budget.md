# Q3 2026 Error Budget Policy

## Overview

Error budgets define the acceptable level of unreliability for each SLO. They balance feature velocity against system stability.

## Budget Allocation

| SLO | Target | Error Budget | Monthly Allowance |
|-----|--------|-------------|-------------------|
| Fraud Scoring Availability | 99.9% | 0.1% | ~43 minutes |
| Investigation Availability | 99.5% | 0.5% | ~3.6 hours |
| Dashboard Availability | 99.5% | 0.5% | ~3.6 hours |

## Budget Consumption Actions

| Consumption | Action |
|-------------|--------|
| > 50% in first half | Freeze non-critical deployments |
| > 75% | All deployments require SRE approval |
| 100% | Feature freeze until next budget window |

## Quarterly Review

- Review budget consumption at end of each month
- Adjust SLO targets if consistently under/over consumed
- Document learnings and adjust processes
