# Agent System

## Reality check (2026-07-31)

The agents in `agents/` are the source of truth. Earlier design docs described
8 agents (risk, pattern, behavior, history, network, compliance, decision) that
do **not exist in the codebase** — those roles are covered by the L1 rule
engine and ensemble fusion instead. This document reflects what actually runs.

## Modules

14 modules — 12 concrete `BaseAgent` subclasses + `MessageRouter` + `OrchestratorState`.

| Module | Class | Role | Status |
|--------|-------|------|--------|
| `base.py` | `BaseAgent` | Abstract contract: config, message loop, error handling | core |
| `transaction_agent.py` | `TransactionAnalysisAgent` | Analyzes a single transaction: features, rules, anomaly flags | live |
| `profile_agent.py` | `ProfileAgent` | Maintains user risk profiles from transaction history | live |
| `planner_agent.py` | `PlannerAgent` | Breaks complex investigations into ordered sub-tasks | stub — only `COMPLEX_INVESTIGATION_REQUEST` |
| `memory_agent.py` | `MemoryAgent` | Stores/retrieves investigation context across sessions | live |
| `human_review_agent.py` | `HumanReviewAgent` | Ingests analyst feedback into the decision loop | live |
| `reflection_agent.py` | `ReflectionAgent` | Nightly FP clustering + drift detection + auto-tune recommendations | live |
| `critic_agent.py` | `CriticAgent` | Challenges decisions, tracks challenge accuracy vs. feedback | partial — accuracy tracking not wired to live scoring |
| `mitigation_agent.py` | `MitigationAgent` | Executes automated block/chill/rollback actions with confirmation | live |
| `collective_agent.py` | `CollectiveIntelligenceAgent` | Coordinated multi-agent assessment (swarm voting, not a router) | partial — assessment + feedback only, no live swarm consensus |
| `monitoring_agent.py` | `MonitoringAgent` | Heartbeats, performance reports, agent health checks | live |
| `validation_agent.py` | `ValidationAgent` | Schema + rule validation on agent messages | live |
| `message.py` | `MessageRouter` | Message routing, priority, correlation | infra |
| `state.py` | `OrchestratorState` | Orchestration state machine | infra |

## Communication

Agents exchange `AgentMessage`s through `MessageRouter`:

```
investigation task → transaction_agent → (profile|memory|planner)
                   → collective_agent (assessment) → critic_agent
                   → mitigation_agent (actions, confirmed)
                   → human_review_agent (feedback) → reflection_agent (nightly)
```

Each concrete agent implements `async def process(message) -> AgentMessage`
and returns an error response for unexpected message types.

## What is not here

- `risk_agent`, `pattern_agent`, `behavior_agent`, `history_agent`,
  `network_agent`, `compliance_agent`, `decision_agent` — described in early
  design docs but never implemented; their responsibilities live in
  `engine/statistical_filter.py`, `engine/ensemble.py`, and `ml/model.py`.
