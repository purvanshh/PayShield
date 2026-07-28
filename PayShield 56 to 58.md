
content = """# PayShield — 60-Phase Enterprise Implementation Plan

## Phases 56–60: Post-Release SRE, Continuous Improvement, Advanced Agents, Compliance & Long-Term Maintenance

**Document Version:** 1.0  
**Classification:** Internal Engineering Blueprint  
**Author:** Purvansh Sahu  
**Date:** July 29, 2026  
**Scope:** Phases 56–60 of 60

---

## Table of Contents

- [Phase 56: Post-Release SRE, SLOs & Chaos Engineering](#phase-56)
- [Phase 57: Model A/B Testing & Continuous Improvement Framework](#phase-57)
- [Phase 58: Advanced Multi-Agent Ecosystem — Planner, Critic & Reflection Agents](#phase-58)
- [Phase 59: Regulatory Compliance Automation — PCI-DSS, RBI & EU AI Act](#phase-59)
- [Phase 60: Final Architecture Review, Performance Optimization & Maintenance Roadmap](#phase-60)

---

## Phase 56: Post-Release SRE, SLOs & Chaos Engineering

### 1. Phase Number & Title
**Phase 56** — Post-Release SRE, SLOs & Chaos Engineering

### 2. Objective
Establish Site Reliability Engineering (SRE) practices including Service Level Objectives (SLOs), error budgets, on-call runbooks, incident management playbooks, and chaos engineering experiments to validate system resilience under failure conditions.

### 3. Why This Phase Exists
Deploying to production is not the finish line — it is the starting line. Without SLOs, the team cannot distinguish between "working" and "barely working." Without error budgets, there is no mechanism to balance reliability against feature velocity. Without chaos engineering, resilience is assumed rather than proven. This phase transforms PayShield from a deployed system into an operationally mature platform that can survive node failures, network partitions, and dependency outages without data loss or decision degradation.

### 4. Prerequisites
Phases 1–55 complete. System in production for minimum 48-hour burn-in. Monitoring stack (Prometheus, Grafana, Alertmanager) fully operational.

### 5. Detailed Implementation Steps

1. Create `sre/` directory:
   ```
   sre/
   ├── slos/
   │   ├── fraud-scoring-slo.md
   │   ├── investigation-slo.md
   │   └── dashboard-slo.md
   ├── error-budgets/
   │   └── q3-2026-error-budget.md
   ├── runbooks/
   │   ├── on-call-rotation.md
   │   ├── incident-commander-playbook.md
   │   ├── post-mortem-template.md
   │   └── escalation-policy.md
   ├── chaos/
   │   ├── experiments/
   │   │   ├── api-pod-failure.yaml
   │   │   ├── redis-network-partition.yaml
   │   │   ├── postgres-high-latency.yaml
   │   │   ├── neo4j-node-drain.yaml
   │   │   └── ollama-resource-exhaustion.yaml
   │   └── litmus-chaos-setup.md
   └── README.md
   ```

2. Define SLOs in `sre/slos/fraud-scoring-slo.md`:
   - **Availability:** 99.9% of `/v1/score` requests return non-5xx responses over 30-day window
   - **Latency:** p99 < 100 ms for single-transaction scoring; p99 < 500 ms for batch-100
   - **Throughput:** Sustain 1000 TPS without latency degradation
   - **Correctness:** False positive rate < 5% at 90% recall (measured weekly on analyst feedback)
   - **Freshness:** Investigation reports generated within 60 seconds of BLOCK decision for 99% of transactions

3. Implement error budget policy:
   - Error budget = 1 - SLO (e.g., 0.1% for 99.9% availability = ~43 minutes downtime per month)
   - If error budget consumed > 50% in first half of month: freeze non-critical deployments
   - If error budget consumed > 75%: all deployments require SRE approval; incident response team activated
   - If error budget consumed 100%: feature freeze until next budget window; focus on reliability work only
   - Document in `sre/error-budgets/q3-2026-error-budget.md`

4. Implement on-call rotation:
   - Primary/secondary rotation via PagerDuty or Opsgenie
   - Rotation period: 1 week
   - Handoff meeting: 30 minutes every Monday documenting ongoing issues
   - On-call engineer has: SSH access to cluster, admin API credentials (break-glass), direct line to engineering lead
   - Escalation: 5 minutes no response → secondary; 10 minutes → engineering manager; 15 minutes → CTO

5. Create incident management playbook (`sre/runbooks/incident-commander-playbook.md`):
   - SEV1 (revenue-impacting, data loss): all-hands war room, page CTO, public status page updated every 15 minutes
   - SEV2 (degraded service, workaround exists): page on-call + engineering lead, internal status update every 30 minutes
   - SEV3 (minor degradation, no customer impact): ticket for next business day
   - Incident commander responsibilities: communication, coordination, decision authority, post-mortem scheduling

6. Implement chaos engineering with LitmusChaos or Gremlin:
   - **Experiment 1 — API Pod Failure:** Kill 1 of 3 API pods randomly every 10 minutes for 1 hour. Verify HPA replaces pod within 60 seconds and p99 latency remains < 100 ms.
   - **Experiment 2 — Redis Network Partition:** Isolate Redis pod from API pods for 30 seconds. Verify circuit breaker opens, fallback cache activates, and no transactions are lost (queued for retry).
   - **Experiment 3 — PostgreSQL High Latency:** Inject 200ms latency into PostgreSQL network via `tc`. Verify API degrades gracefully (returns 503 on non-critical endpoints), audit log writes buffered in Redis.
   - **Experiment 4 — Neo4j Node Drain:** Drain node running Neo4j pod. Verify StatefulSet reschedules to new node, graph snapshot restores, and GNN inference resumes within 5 minutes.
   - **Experiment 5 — Ollama Resource Exhaustion:** Limit Ollama CPU to 100m. Verify LLM investigations queue but do not block scoring hot path; fallback narratives generated for critical alerts.

7. Create post-mortem template (`sre/runbooks/post-mortem-template.md`):
   - Timeline (detailed, minute-by-minute)
   - Root cause analysis (5 Whys)
   - Impact assessment (transactions affected, revenue at risk, analyst hours lost)
   - Action items (with owners and due dates)
   - Lessons learned
   - Blameless culture statement

8. Add `scripts/chaos-run.py`:
   - Automated chaos experiment runner
   - Pre-check: verify SLOs are currently green
   - Run experiment for defined duration
   - Post-check: verify SLOs recover within acceptable window
   - Generate experiment report with pass/fail
   - Abort experiment automatically if SLO breach exceeds error budget

9. Implement Service Level Indicators (SLIs) in Prometheus:
   - `slo:availability:ratio_30d` — ratio of successful requests
   - `slo:latency:p99_30d` — 30-day rolling p99 latency
   - `slo:correctness:false_positive_rate_7d` — weekly FP rate
   - Grafana dashboard: "SLO Compliance" with burn-down charts

10. Add error budget burn rate alerts:
    - Burn rate > 14.4x (consumes 2% budget in 1 hour) → page on-call immediately
    - Burn rate > 6x (consumes 5% budget in 6 hours) → page on-call
    - Burn rate > 2x (consumes 10% budget in 3 days) → ticket for next business day

### 6. Directory Structure Changes
```
payshield/
├── sre/
│   ├── slos/
│   │   ├── fraud-scoring-slo.md
│   │   ├── investigation-slo.md
│   │   └── dashboard-slo.md
│   ├── error-budgets/
│   │   └── q3-2026-error-budget.md
│   ├── runbooks/
│   │   ├── on-call-rotation.md
│   │   ├── incident-commander-playbook.md
│   │   ├── post-mortem-template.md
│   │   └── escalation-policy.md
│   ├── chaos/
│   │   ├── experiments/
│   │   │   ├── api-pod-failure.yaml
│   │   │   ├── redis-network-partition.yaml
│   │   │   ├── postgres-high-latency.yaml
│   │   │   ├── neo4j-node-drain.yaml
│   │   │   └── ollama-resource-exhaustion.yaml
│   │   └── litmus-chaos-setup.md
│   └── README.md
├── scripts/
│   └── chaos-run.py
```

### 7. Files to Create
- All files in `sre/` directory structure
- `scripts/chaos-run.py`

### 8. Files to Modify
- `Makefile` (add `make chaos-test` target)
- `.github/workflows/ci.yml` (add chaos test gate for staging environment)

### 9. Major Classes/Modules/Components
- `SLOTracker` — Prometheus recording rules for SLI computation.
- `ErrorBudgetCalculator` — Burn rate and budget consumption analyzer.
- `ChaosOrchestrator` — Automated chaos experiment runner.
- `IncidentManager` — Incident lifecycle coordination.

### 10. Functions and APIs to Implement
- `ChaosOrchestrator.run_experiment(config) -> ExperimentReport`
- `ChaosOrchestrator.pre_check() -> bool`
- `ChaosOrchestrator.post_check() -> bool`
- `ErrorBudgetCalculator.get_burn_rate(slo, window) -> float`
- `ErrorBudgetCalculator.is_budget_exhausted() -> bool`

### 11. Database/Schema Changes
None.

### 12. Agent Architecture Updates
`MonitoringAgent` (Phase 40) extended to track SLO compliance and emit alerts on budget consumption.

### 13. Prompt Engineering Considerations
None.

### 14. RAG/Vector Database Changes
None.

### 15. Infrastructure Requirements
LitmusChaos 3.0+ or Gremlin, PagerDuty/Opsgenie, dedicated staging cluster for chaos experiments.

### 16. Security Considerations
- Chaos experiments run only in staging/isolated environment; never in production
- Experiment abort criteria must prevent actual data loss or corruption
- On-call credentials stored in break-glass vault (1Password, Vault by HashiCorp)
- Incident communications must not leak sensitive customer data

### 17. Logging and Observability
- Prometheus: `slo_compliance_ratio`, `error_budget_remaining_ratio`, `chaos_experiments_total`
- Grafana: SLO dashboard with burn-down charts, incident timeline overlay
- PagerDuty: Automated paging based on burn rate thresholds
- All incidents logged to `incidents/` directory with structured JSON

### 18. Testing Strategy
- Unit test: `test_slo_calculation` — verify SLI math correct
- Unit test: `test_error_budget_exhaustion` — verify freeze triggered at 100%
- Integration test: `test_chaos_api_pod_failure` — kill pod, verify HPA recovery
- Integration test: `test_chaos_redis_partition` — verify circuit breaker activates
- Quarterly: Full chaos day (game day) with all experiments run sequentially

### 19. Expected Output/Deliverables
- 3 documented SLOs with SLI queries
- Error budget policy with automatic deployment freeze triggers
- 5 chaos engineering experiments with automated runners
- Incident management playbook and post-mortem template
- On-call rotation schedule

### 20. Definition of Done (DoD)
- [ ] All SLOs defined with measurable SLIs in Prometheus
- [ ] Error budget policy documented and approved
- [ ] On-call rotation established with escalation policy
- [ ] 5 chaos experiments run successfully in staging
- [ ] Chaos experiments do not breach SLOs during normal operation
- [ ] Incident commander playbook reviewed by all engineers
- [ ] Post-mortem template used for at least 1 simulated incident
- [ ] SLO dashboard live in Grafana
- [ ] All tests pass

---

## Phase 57: Model A/B Testing & Continuous Improvement Framework

### 1. Phase Number & Title
**Phase 57** — Model A/B Testing & Continuous Improvement Framework

### 2. Objective
Implement a production-grade A/B testing framework for fraud detection models and statistical rules, including shadow mode, champion/challenger pattern, automated performance evaluation, and safe promotion/rollback procedures.

### 3. Why This Phase Exists
Machine learning models degrade over time — a phenomenon known as model drift. A model that scores 0.94 AUC-ROC at launch may drop to 0.85 within 6 months as fraudsters adapt. Rule-based systems also suffer from concept drift. Without a systematic A/B testing framework, teams either never update models (stagnation) or deploy untested changes (risk). This phase establishes the "assembly line" for continuous model improvement: train challenger → evaluate in shadow → A/B test with traffic split → promote or rollback.

### 4. Prerequisites
Phases 27–28 (training pipeline and model registry), Phase 31 (ensemble fusion), Phase 40 (HumanReviewAgent), and Phase 55 (release) complete. Production traffic flowing.

### 5. Detailed Implementation Steps

1. Create `payshield/ml/ab_testing.py` and `payshield/ml/continuous_improvement.py`.
2. Implement `ABTestFramework`:
   - `register_experiment(name: str, challenger_version: str, traffic_split: float, duration_days: int) -> Experiment`
   - Traffic split: 0% (shadow), 1–10% (canary), 50% (A/B), 100% (full rollout)
   - Experiment types: `MODEL_CHALLENGER`, `RULE_UPDATE`, `THRESHOLD_TUNING`, `FEATURE_ABLATION`
   - Store experiment state in PostgreSQL `ab_experiments` table
3. Implement shadow mode:
   - Challenger model runs in parallel with champion (production) model
   - Challenger predictions logged but not acted upon
   - Compare challenger vs champion on: AUC-ROC, AUC-PR, false positive rate, latency
   - Shadow mode runs for minimum 7 days or 100K transactions
4. Implement canary deployment:
   - Route 1% of traffic to challenger model
   - Champion still makes the actual decision
   - Monitor for latency spikes, error rates, or decision divergence > 10%
   - Auto-rollback if p99 latency increases > 20% or error rate > 0.1%
5. Implement A/B test evaluation:
   - Route 50% traffic to champion, 50% to challenger
   - Decisions from both models are executed (requires business approval for financial risk)
   - Measure: fraud catch rate, false positive rate, analyst overturn rate, FVaR
   - Statistical significance test: Welch's t-test on FVaR difference, p < 0.05 required
6. Implement automated promotion/rollback:
   - If challenger beats champion on primary metric (FVaR) with statistical significance: auto-promote via `ModelRegistry.promote()` (Phase 28)
   - If challenger underperforms or causes incidents: auto-rollback within 60 seconds
   - All promotions/rollbacks logged to `ab_experiment_events` table
7. Implement `ContinuousImprovementLoop`:
   - Weekly automated retraining trigger: if `feedback_submissions_total{category="FALSE_POSITIVE"}` > threshold OR PSI > 0.25 OR model age > 30 days
   - Trigger: `scripts/train_gnn.py --auto --base-model current_production`
   - New model automatically enters shadow mode
   - Human approval required for canary and A/B stages
8. Implement `RuleABTesting`:
   - Statistical rules can be A/B tested in shadow mode
   - New rules evaluated alongside old rules; disagreement logged
   - If new rule catches fraud without increasing FP rate: promoted via `/admin/rules/reload`
9. Add `payshield/api/routes/experiments.py`:
   - `POST /admin/experiments` — create new experiment (admin only)
   - `GET /admin/experiments` — list active and historical experiments
   - `GET /admin/experiments/{id}/results` — real-time experiment metrics
   - `POST /admin/experiments/{id}/promote` — manual promotion
   - `POST /admin/experiments/{id}/rollback` — manual rollback
10. Add experiment dashboard panels:
    - Grafana panel: "Model A/B Test — FVaR Comparison" with champion vs challenger lines
    - Grafana panel: "Shadow Mode Divergence" — percentage of decisions that differ
    - Grafana panel: "Experiment Health" — latency, error rate, traffic split accuracy
11. Implement `ExperimentGuardrails`:
    - Maximum 1 active A/B test at a time (prevents interaction effects)
    - Minimum 7 days shadow mode before canary
    - Auto-rollback on any SEV2+ incident during experiment
    - Business stakeholder approval required for > 10% traffic split

### 6. Directory Structure Changes
```
payshield/
├── payshield/
│   └── ml/
│       ├── ab_testing.py
│       └── continuous_improvement.py
├── payshield/
│   └── api/
│       └── routes/
│           └── experiments.py
├── sre/
│   └── dashboards/
│       └── ab-test-dashboard.json
```

### 7. Files to Create
- `payshield/ml/ab_testing.py`
- `payshield/ml/continuous_improvement.py`
- `payshield/api/routes/experiments.py`
- `sre/dashboards/ab-test-dashboard.json`

### 8. Files to Modify
- `payshield/api/main.py` (include experiments router)
- `payshield/ml/registry.py` (add experiment-aware promotion)
- `Makefile` (add `make trigger-retrain`)

### 9. Major Classes/Modules/Components
- `ABTestFramework` — Experiment registration, traffic routing, and evaluation.
- `ContinuousImprovementLoop` — Automated retraining trigger.
- `ExperimentGuardrails` — Safety limits and auto-rollback.
- `RuleABTesting` — Statistical rule shadow evaluation.

### 10. Functions and APIs to Implement
- `ABTestFramework.register_experiment(name, challenger_version, traffic_split, duration) -> Experiment`
- `ABTestFramework.evaluate_experiment(id) -> ExperimentResult`
- `ABTestFramework.promote(id) -> None`
- `ABTestFramework.rollback(id) -> None`
- `ContinuousImprovementLoop.check_retrain_trigger() -> bool`
- `ContinuousImprovementLoop.trigger_retrain() -> str` (returns new model version)
- `POST /admin/experiments` → `ExperimentResponse`
- `GET /admin/experiments/{id}/results` → `ExperimentMetricsResponse`

### 11. Database/Schema Changes
- PostgreSQL table: `ab_experiments`
  - `experiment_id` UUID PRIMARY KEY
  - `name` VARCHAR(100) NOT NULL
  - `experiment_type` VARCHAR(20) NOT NULL
  - `champion_version` VARCHAR(20) NOT NULL
  - `challenger_version` VARCHAR(20) NOT NULL
  - `traffic_split` FLOAT NOT NULL CHECK (traffic_split BETWEEN 0 AND 1)
  - `status` VARCHAR(20) DEFAULT 'shadow'
  - `start_date` TIMESTAMP NOT NULL
  - `end_date` TIMESTAMP
  - `created_by` VARCHAR(50) NOT NULL
  - `created_at` TIMESTAMP DEFAULT NOW()
- PostgreSQL table: `ab_experiment_events`
  - `event_id` BIGSERIAL PRIMARY KEY
  - `experiment_id` UUID REFERENCES ab_experiments
  - `event_type` VARCHAR(20) NOT NULL
  - `payload_json` JSONB
  - `created_at` TIMESTAMP DEFAULT NOW()

### 12. Agent Architecture Updates
`HumanReviewAgent` (Phase 40) provides feedback data that feeds into `ContinuousImprovementLoop`. `MonitoringAgent` tracks experiment health and can auto-rollback on anomaly detection.

### 13. Prompt Engineering Considerations
Prompt A/B testing supported: `PromptBuilder` (Phase 33) extended to support versioned prompt experiments where two prompt templates run in shadow mode, output quality scored by deterministic parser (Phase 35).

### 14. RAG/Vector Database Changes
None.

### 15. Infrastructure Requirements
Additional compute for shadow/challenger models (can run on spot instances). PostgreSQL for experiment state storage.

### 16. Security Considerations
- A/B tests on financial decisions require business stakeholder sign-off
- Shadow mode must not leak challenger decisions to downstream systems
- Experiment data contains production transaction patterns — access restricted to ML engineers and admins
- Auto-rollback must be immediate and irreversible to prevent prolonged bad decisions

### 17. Logging and Observability
- Prometheus: `ab_test_decisions_total` (labeled by experiment, model), `ab_test_latency_seconds`, `ab_test_divergence_ratio`
- Grafana: dedicated A/B test dashboard with real-time metrics
- Log every experiment state change with full context

### 18. Testing Strategy
- Unit test: `test_shadow_mode_logs_only` — verify challenger decisions not acted upon
- Unit test: `test_canary_auto_rollback` — simulate latency spike, verify rollback
- Unit test: `test_statistical_significance` — verify Welch's t-test computation
- Integration test: `test_full_ab_test_lifecycle` — shadow → canary → A/B → promote
- Integration test: `test_continuous_retrain_trigger` — simulate drift, verify retrain triggered

### 19. Expected Output/Deliverables
- A/B testing framework with shadow, canary, and full A/B modes
- Automated retraining triggers based on drift and feedback
- Experiment management API with 4 endpoints
- Grafana dashboard for real-time experiment monitoring
- Guardrails preventing unsafe experiment configurations

### 20. Definition of Done (DoD)
- [ ] Shadow mode runs challenger model without affecting decisions
- [ ] Canary mode routes 1% traffic with auto-rollback on degradation
- [ ] A/B test evaluates statistical significance on FVaR
- [ ] Auto-promotion works when challenger beats champion
- [ ] Auto-rollback triggers within 60 seconds on incident
- [ ] Continuous improvement loop detects drift and triggers retrain
- [ ] Experiment API returns real-time metrics
- [ ] Maximum 1 active A/B test enforced
- [ ] All tests pass

---

## Phase 58: Advanced Multi-Agent Ecosystem — Planner, Critic & Reflection Agents

### 1. Phase Number & Title
**Phase 58** — Advanced Multi-Agent Ecosystem — Planner, Critic & Reflection Agents

### 2. Objective
Expand the 8-agent multi-agent system (Phases 37–40) with advanced cognitive agents: a Planner Agent for complex investigation strategies, a Critic Agent for decision quality assurance, a Reflection Agent for self-improvement, and a Validation Agent for output verification.

### 3. Why This Phase Exists
The original 8-agent system (Profile, Transaction, Collective, Mitigation, Memory, Human Review, Monitoring, Compliance) handles operational fraud detection well but lacks higher-order reasoning. The Planner Agent decomposes complex multi-step fraud investigations. The Critic Agent challenges weak decisions before they are executed. The Reflection Agent analyzes past mistakes to improve future reasoning. The Validation Agent ensures agent outputs conform to schema and business rules. These agents transform PayShield from a reactive detection system into a self-improving cognitive platform.

### 4. Prerequisites
Phases 37–40 complete. All base agent infrastructure (`BaseAgent`, `MessageRouter`, `OrchestratorState`) operational. LLM Investigator (Phases 32–36) and HumanReviewAgent (Phase 40) providing feedback data.

### 5. Detailed Implementation Steps

1. Create `payshield/agents/planner_agent.py`.
2. Implement `PlannerAgent` (extends `BaseAgent`):
   - `agent_type = "PLANNER"`
   - Receives `COMPLEX_INVESTIGATION_REQUEST` when ensemble confidence is borderline (0.70–0.85) or multiple conflicting signals exist
   - Decomposes investigation into sub-tasks:
     - "Verify device fingerprint history"
     - "Check merchant Benford deviation over 14 days"
     - "Analyze correlated transactions within 1-hour window"
     - "Query memory for similar historical patterns"
   - Assigns sub-tasks to appropriate agents via `MessageRouter`
   - Aggregates sub-task results into unified investigation plan
   - Outputs `INVESTIGATION_PLAN` with ordered evidence collection steps
   - Uses tree-of-thought reasoning: generates 3 investigation strategies, scores each by expected information gain, selects optimal plan

3. Create `payshield/agents/critic_agent.py`.
4. Implement `CriticAgent` (extends `BaseAgent`):
   - `agent_type = "CRITIC"`
   - Subscribes to `COLLECTIVE_DECISION` events from `CollectiveIntelligenceAgent` (Phase 39)
   - Challenges decisions that meet any of:
     - Confidence < 0.80 but action is BLOCK
     - Single agent dissent in collective vote
     - Historical false positive rate for this pattern > 10%
     - Amount is > 20x user median but user has VIP status
   - Requests additional evidence from `PlannerAgent` or `MemoryAgent`
   - Emits `DECISION_CHALLENGE` with reasoning; if challenge upheld, decision downgraded from BLOCK to REVIEW
   - Maintains challenge accuracy: tracks when challenges were correct vs incorrect, adjusts aggression threshold dynamically

5. Create `payshield/agents/reflection_agent.py`.
6. Implement `ReflectionAgent` (extends `BaseAgent`):
   - `agent_type = "REFLECTION"`
   - Runs nightly batch job (via Celery beat) analyzing previous 24 hours of decisions
   - Identifies patterns in analyst feedback:
     - "False positives clustered around merchant category X"
     - "GNN over-predicts fraud for new users (< 7 days)"
     - "Statistical filter triggers too aggressively on salary-day transactions"
   - Generates `REFLECTION_REPORT` with:
     - Identified weaknesses per agent
     - Recommended threshold adjustments
     - Suggested new rule candidates
     - Training data augmentation recommendations
   - Submits recommendations to `HumanReviewAgent` for approval
   - Approved recommendations automatically update agent configurations (with audit log)

7. Create `payshield/agents/validation_agent.py`.
8. Implement `ValidationAgent` (extends `BaseAgent`):
   - `agent_type = "VALIDATION"`
   - Acts as a gatekeeper before any action reaches `MitigationAgent` (Phase 39)
   - Validates:
     - Decision schema compliance (ALLOW/BLOCK/REVIEW only)
     - Confidence score in [0, 1]
     - Required evidence present (minimum 2 evidence items for BLOCK)
     - No contradictory evidence (e.g., geo-velocity says impossible travel but device fingerprint matches home device)
     - PII not present in decision payload
   - If validation fails: emits `VALIDATION_FAILURE` → decision blocked → escalates to `HumanReviewAgent`
   - Maintains validation failure rate per agent; agents with > 1% failure rate flagged for review

9. Implement agent communication protocol extensions:
   - New message types: `COMPLEX_INVESTIGATION_REQUEST`, `INVESTIGATION_PLAN`, `DECISION_CHALLENGE`, `REFLECTION_REPORT`, `VALIDATION_FAILURE`
   - Priority routing: `DECISION_CHALLENGE` and `VALIDATION_FAILURE` have priority 1 (highest)
   - Timeout handling: PlannerAgent sub-tasks have 30-second timeout; if exceeded, partial results used

10. Add `scripts/test_advanced_agents.py` for interaction testing:
    - Simulate complex fraud case with conflicting signals
    - Verify PlannerAgent decomposes correctly
    - Verify CriticAgent challenges weak BLOCK decisions
    - Verify ReflectionAgent identifies false positive patterns
    - Verify ValidationAgent catches schema violations

11. Update `payshield/agents/__init__.py` to register all 12 agents:
    - Original 8: Profile, Transaction, Collective, Mitigation, Memory, HumanReview, Monitoring, Compliance
    - New 4: Planner, Critic, Reflection, Validation

### 6. Directory Structure Changes
```
payshield/
├── payshield/
│   └── agents/
│       ├── planner_agent.py
│       ├── critic_agent.py
│       ├── reflection_agent.py
│       └── validation_agent.py
```

### 7. Files to Create
- `payshield/agents/planner_agent.py`
- `payshield/agents/critic_agent.py`
- `payshield/agents/reflection_agent.py`
- `payshield/agents/validation_agent.py`
- `scripts/test_advanced_agents.py`

### 8. Files to Modify
- `payshield/agents/__init__.py` (register new agents)
- `payshield/agents/message.py` (add new message types)
- `payshield/tasks/celery_app.py` (add ReflectionAgent nightly beat schedule)

### 9. Major Classes/Modules/Components
- `PlannerAgent` — Complex investigation strategy decomposition.
- `CriticAgent` — Decision quality challenge and review.
- `ReflectionAgent` — Nightly self-improvement analysis.
- `ValidationAgent` — Pre-action schema and logic gatekeeper.

### 10. Functions and APIs to Implement
- `PlannerAgent.decompose_investigation(context) -> InvestigationPlan`
- `PlannerAgent.assign_subtasks(plan) -> list[AgentMessage]`
- `CriticAgent.evaluate_decision(decision) -> CriticResult`
- `CriticAgent.challenge_decision(decision) -> DecisionChallenge`
- `ReflectionAgent.analyze_period(start, end) -> ReflectionReport`
- `ReflectionAgent.generate_recommendations(report) -> list[ConfigChange]`
- `ValidationAgent.validate(decision) -> ValidationResult`
- `ValidationAgent.check_contradictions(evidence) -> list[Contradiction]`

### 11. Database/Schema Changes
- PostgreSQL table: `reflection_reports`
  - `report_id` BIGSERIAL PRIMARY KEY
  - `period_start` TIMESTAMP NOT NULL
  - `period_end` TIMESTAMP NOT NULL
  - `findings_json` JSONB NOT NULL
  - `recommendations_json` JSONB
  - `approved_by` VARCHAR(50)
  - `created_at` TIMESTAMP DEFAULT NOW()
- PostgreSQL table: `validation_failures`
  - `failure_id` BIGSERIAL PRIMARY KEY
  - `txn_id_hash` VARCHAR(64)
  - `agent_id` VARCHAR(50) NOT NULL
  - `failure_type` VARCHAR(50) NOT NULL
  - `details_json` JSONB
  - `created_at` TIMESTAMP DEFAULT NOW()

### 12. Agent Architecture Updates
This phase expands the ecosystem from 8 to 12 agents. The ValidationAgent sits between CollectiveIntelligenceAgent and MitigationAgent as a mandatory gate. The CriticAgent feeds back into the CollectiveIntelligenceAgent loop. The ReflectionAgent operates asynchronously via Celery beat.

### 13. Prompt Engineering Considerations
- PlannerAgent uses structured LLM prompts with chain-of-thought reasoning
- ReflectionAgent uses few-shot examples of past false positives to guide pattern identification
- All agent prompts versioned in `prompts/manifest.yaml` (Phase 33)

### 14. RAG/Vector Database Changes
ReflectionAgent queries `fraud_patterns` vector collection (Phase 40) to find semantically similar historical cases during analysis.

### 15. Infrastructure Requirements
Redis (for message routing), PostgreSQL (for reflection reports), Celery beat (for nightly jobs).

### 16. Security Considerations
- ValidationAgent prevents malicious or corrupted agent outputs from reaching MitigationAgent
- ReflectionAgent recommendations require human approval before auto-deployment
- CriticAgent challenges logged immutably for audit
- PlannerAgent sub-task assignments must not leak PII between agents

### 17. Logging and Observability
- Prometheus: `planner_subtasks_total`, `critic_challenges_total`, `reflection_reports_generated_total`, `validation_failures_total`
- Log every agent interaction with full message trace for debugging
- Grafana dashboard: "Advanced Agent Ecosystem" showing message flows and decision quality trends

### 18. Testing Strategy
- Unit test: `test_planner_decomposes_complex_case` — verify 3+ sub-tasks generated
- Unit test: `test_critic_challenges_weak_block` — verify confidence < 0.80 BLOCK challenged
- Unit test: `test_reflection_identifies_fp_pattern` — verify pattern detection from feedback
- Unit test: `test_validation_blocks_schema_violation` — verify invalid decision rejected
- Unit test: `test_validation_catches_contradiction` — verify conflicting evidence flagged
- Integration test: `test_full_agent_pipeline_with_critic` — end-to-end with challenge and resolution

### 19. Expected Output/Deliverables
- 4 new advanced agents (Planner, Critic, Reflection, Validation)
- 12-agent ecosystem fully operational
- Nightly reflection reports with improvement recommendations
- Validation gate preventing bad decisions
- Critic-driven decision quality improvement

### 20. Definition of Done (DoD)
- [ ] PlannerAgent decomposes complex investigations into sub-tasks
- [ ] CriticAgent challenges weak BLOCK decisions and tracks accuracy
- [ ] ReflectionAgent generates nightly reports with actionable recommendations
- [ ] ValidationAgent blocks schema violations and contradictions before action
- [ ] All 12 agents communicate via MessageRouter without errors
- [ ] Reflection recommendations require human approval before deployment
- [ ] Advanced agent latency added < 20 ms to hot path (ValidationAgent only)
- [ ] All tests pass

---

## Phase 59: Regulatory Compliance Automation — PCI-DSS, RBI & EU AI Act

### 1. Phase Number & Title
**Phase 59** — Regulatory Compliance Automation — PCI-DSS, RBI & EU AI Act

### 2. Objective
Implement automated compliance checks, audit report generation, and regulatory evidence collection for PCI-DSS (payment card industry data security), RBI (Reserve Bank of India) data localization and AI guidelines, and EU AI Act (high-risk AI system requirements).

### 3. Why This Phase Exists
Financial fraud detection systems operate under strict regulatory frameworks. PCI-DSS requires encryption, access controls, and audit trails for payment