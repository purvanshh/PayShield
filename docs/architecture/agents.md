# Multi-Agent System Architecture

## Overview

The agent orchestrator manages 8 specialized agents that collaborate on complex fraud decisions. Each agent is an independent service that analyzes specific aspects of a transaction.

## Agent Communication

```
Orchestrator receives borderline transaction
         │
         ├──→ Transaction Agent (parallel)
         ├──→ Risk Agent (parallel)
         ├──→ Pattern Agent (parallel)
         ├──→ Behavior Agent (parallel)
         ├──→ History Agent (parallel)
         ├──→ Network Agent (parallel)
         ├──→ Compliance Agent (parallel)
         │
         └──→ Decision Agent (after all results)
```

## Agent Specifications

### 1. Transaction Agent
- **Purpose**: Core transaction analysis
- **Inputs**: Raw transaction data, features
- **Outputs**: Anomaly score, suspicious indicators
- **Methods**: Statistical outlier detection, rule matching

### 2. Risk Agent
- **Purpose**: Risk scoring and aggregation
- **Inputs**: All agent outputs
- **Outputs**: Unified risk score (0-100)
- **Methods**: Weighted aggregation, Bayesian updating

### 3. Pattern Agent
- **Purpose**: Pattern matching and anomaly detection
- **Inputs**: Transaction patterns, user history
- **Outputs**: Pattern match confidence
- **Methods**: Time-series analysis, sequence matching

### 4. Behavior Agent
- **Purpose**: Behavioral analysis
- **Inputs**: User behavior profile
- **Outputs**: Behavioral deviation score
- **Methods**: Baseline comparison, velocity checks

### 5. History Agent
- **Purpose**: Historical context lookup
- **Inputs**: User ID, merchant ID
- **Outputs**: Historical summary statistics
- **Methods**: Aggregation queries, trend analysis

### 6. Network Agent
- **Purpose**: Network analysis
- **Inputs**: IP, device, merchant info
- **Outputs**: Network risk score
- **Methods**: Graph analysis, reputation scoring

### 7. Compliance Agent
- **Purpose**: Regulatory checks
- **Inputs**: Transaction details, jurisdiction
- **Outputs**: Compliance flags
- **Methods**: Rule engine, regulatory database

### 8. Decision Agent
- **Purpose**: Final decision synthesis
- **Inputs**: All agent outputs + LLM report
- **Outputs**: Final decision + explanation
- **Methods**: Weighted aggregation, threshold logic

## Orchestration Flow

1. **Receive** transaction from ensemble (confidence 0.5-0.9)
2. **Fan-out** to all 7 analysis agents in parallel
3. **Collect** results with configurable timeout (5s)
4. **Feed** results to LLM investigator for reasoning
5. **Synthesize** final decision via Decision Agent
6. **Return** result with explanation path

## Configuration

```yaml
orchestrator:
  timeout_seconds: 5
  max_retries: 2
  parallel_execution: true
  required_agents: [transaction, risk, decision]
  optional_agents: [pattern, behavior, history, network, compliance]
```
