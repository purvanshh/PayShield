# Agent System

## Reality check (2026-08-24)

The agents in `agents/` are the source of truth. Earlier docs described a
14-agent framework; the live system runs **four agents**, each doing one
thing well. Development-only agents are archived under `agents/archived/`
(kept, not deleted, for transparency). Earlier design-era agents (*risk,
pattern, behavior, history, network, compliance, decision*) never existed in
code — those roles are covered by the L1 rule engine and ensemble fusion.

## Live modules

| Module | Class | Role |
|--------|-------|------|
| `base.py` | `BaseAgent` | Abstract contract: config, message loop, error handling |
| `message.py` | `MessageRouter` | Message routing, priority, correlation |
| `state.py` | `OrchestratorState` | Orchestration state machine |
| `transaction_agent.py` | `TransactionAnalysisAgent` | Extracts order features + evaluates rules |
| `profile_agent.py` | `ProfileAgent` | Maintains user return/order history |
| `reflection_agent.py` | `ReflectionAgent`, `ReflectionReport` | Nightly FP clustering + drift detection + auto-tune recommendations |
| `human_review_agent.py` | `HumanReviewAgent` | Ingests analyst feedback into the decision loop |

`agents/risk_suite_reflection.py` is a pure function module (not an agent)
consumed by the nightly return-risk reflection task.

## Archived modules (`agents/archived/`)

Built during development, not wired to the live path. Full rationale in
`agents/archived/README.md`:

| Module | Status |
|--------|--------|
| `planner_agent.py` | Stub — only `COMPLEX_INVESTIGATION_REQUEST`, no live trigger |
| `collective_agent.py` | Stub — no live swarm consensus; single-agent scoring suffices |
| `critic_agent.py` | Tracking — challenge accuracy not wired to the decision path |
| `mitigation_agent.py` | Deferred — auto-block requires merchant opt-in |
| `monitoring_agent.py` | Replaced — Prometheus + `/admin/agents/health` |
| `validation_agent.py` | Merged — validation lives in Pydantic models |
| `memory_agent.py` | Deferred — persistence not needed for return-risk |

Archived modules keep their original absolute imports and are importable as
`agents.archived.<name>` for future re-wiring.

## Communication

Live agents exchange `AgentMessage`s through `MessageRouter`:

```
order.paid → transaction_agent (features + rules)
           → profile_agent (history update)
           → human_review_agent (analyst overrides)
           → reflection_agent (nightly reweighting)
```

Each concrete agent implements `async def process(message) -> AgentMessage`
and returns an error response for unexpected message types.

## What is not here

- `risk_agent`, `pattern_agent`, `behavior_agent`, `history_agent`,
  `network_agent`, `compliance_agent`, `decision_agent` — described in early
  design docs but never implemented; their responsibilities live in
  `engine/statistical_filter.py`, `engine/ensemble.py`, and `ml/model.py`.
- Live swarm consensus (`collective_agent`) — a research problem, not a
  production path; see `agents/archived/README.md`.