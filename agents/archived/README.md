# Archived Agents

These agents were built during development but are **not wired to the live
scoring path**. They remain in the repo for transparency and future
extension — archiving rather than deleting is an honest record of how the
system evolved.

## Why four live agents

The live system runs exactly four agents, each doing one thing well:

| Agent | Responsibility |
|-------|----------------|
| `transaction_agent` | Extracts order features + evaluates rules |
| `profile_agent` | Maintains user return/order history |
| `reflection_agent` | Nightly false-positive clustering + weight sync |
| `human_review_agent` | Ingests analyst overrides |

Four agents cover 100% of the critical path. The ten modules here were
stubs, monitoring, or experimental orchestration that existing
infrastructure (Prometheus, Pydantic validation, the audit chain) already
covers — keeping them wired into the live path would buy complexity, not
reliability.

## Status per agent

| Agent | Status | Why archived |
|-------|--------|--------------|
| `planner_agent` | Stub | Only handles `COMPLEX_INVESTIGATION_REQUEST`; no live trigger |
| `collective_agent` | Stub | Swarm voting not implemented; single-agent scoring is sufficient |
| `critic_agent` | Tracking | Tracks challenge accuracy but isn't wired to the decision path |
| `mitigation_agent` | Deferred | Auto-block/chill requires merchant opt-in; manual gate for now |
| `monitoring_agent` | Replaced | Prometheus metrics + `/admin/agents/health` cover health |
| `validation_agent` | Merged | Schema validation now lives in the Pydantic models |
| `memory_agent` | Deferred | Investigation context persistence not needed for return-risk |

## Re-enabling

Modules import cleanly (`from agents.archived.<name> import ...`) and keep
their original absolute imports, so re-wiring one is a matter of importing
it from `agents.archived` instead of `agents`. The `agents` namespace
exports only the live agents by design.