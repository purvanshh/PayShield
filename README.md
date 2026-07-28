# PayShield — Real-Time UPI Fraud Detection & Multi-Agent Orchestration

A production-grade fraud detection system purpose-built for **India's UPI digital payment ecosystem**. PayShield targets the attack vectors dominating Indian fintech — mule account rings, velocity burst attacks, merchant collusion, SIM-swap, and device-fingerprint reuse — by combining three detection modalities with a multi-agent orchestration layer.

## Architecture

```
                          POST /score
                              │
                     ┌───────▼────────┐
                     │  L1 Statistical │  < 1 ms
                     │     Filter      │  6 rule types
                     └───────┬────────┘
                             │ (escalated only)
                     ┌───────▼────────┐
                     │  L2 GNN Scorer  │  < 50 ms
                     │  HeteroConv     │
                     └───────┬────────┘
                             │ (blocked/escalated)
                     ┌───────▼────────┐
                     │  Ensemble       │  < 5 ms
                     │  Fusion Engine  │
                     └───────┬────────┘
                             │
               ┌─────────────┼─────────────┐
               ▼             ▼             ▼
         ┌──────────┐ ┌──────────┐ ┌──────────────┐
         │  L3 LLM  │ │  Multi-  │ │  Dashboard   │
         │  Async   │ │  Agent   │ │  & API       │
         │  Celery  │ │  8 Agents│ │  WebSocket   │
         └──────────┘ └──────────┘ └──────────────┘
```

## Performance Targets

| Metric | Target |
|--------|--------|
| p50 inference latency | < 30 ms |
| p99 inference latency | < 100 ms |
| Throughput (single node) | > 1,000 TPS |
| Model AUC-ROC | > 0.92 |
| False positive rate @ 0.90 recall | < 5% |
| Fraud Value at Risk (FVaR) improvement | ₹6.8 Cr/month |

## Detection Layers

### Layer 1 — Statistical Filter
- **Velocity rules:** z-score > 3 on 1h/24h sliding windows (sorted-set)
- **Burst detection:** > 10 transactions in 5 minutes for low-frequency accounts
- **Amount deviation:** > 5x user's 30-day median with elevated velocity
- **Geo-impossible:** haversine > 900 km/h between consecutive transactions
- **Benford's Law:** χ² > 15.51 on merchant first-digit distribution (n > 20)
- **Device fingerprint:** Jaccard similarity on shared device clusters
- **Decision gate:** configurable BLOCK / ESCALATE / ALLOW rules in YAML

### Layer 2 — Graph Neural Network
- **Node types:** User, Merchant, Device, Transaction
- **Edge types:** performed, to, used, transfer, shared_by
- **Model:** 2-layer HeteroConv GraphSAGE with mean aggregation
- **Readout:** Global mean pooling → 2-layer MLP → sigmoid
- **Explainer:** GNNExplainer (node/edge masks) + SHAP Bridge (tabular features)
- **Calibration:** Isotonic regression on validation set

### Layer 3 — LLM Investigator (Async)
- **Model:** Llama 3.1 8B via Ollama (local, no API cost)
- **Prompt engineering:** Jinja2 templates with 3-shot examples
- **Evidence pipeline:** ranking, dedup, severity scoring from 6 sources
- **Output:** Structured JSON via regex + validation + fallback generator
- **Worker:** Celery async queue with Redis broker, retry, dead-letter

### Ensemble Fusion
- Weighted L1 (0.3) + L2 (0.7) fusion with L1 hard-block override
- L1 ESCALATE boosts L2 score by +0.15
- Disagreement logging (L1 ALLOW vs L2 BLOCK)
- Confidence calibration via IsotonicRegression

### Multi-Agent Orchestration (8 Agents)
| Agent | Type | Function |
|-------|------|----------|
| Profile | PROFILE | Behavioral profiling, drift detection |
| Transaction Analysis | TRANSACTION | Velocity, split detection, merchant risk |
| Collective Intelligence | COLLECTIVE | Bayesian weighted signal fusion |
| Mitigation | MITIGATION | Action execution, dual confirmation, rollback |
| Memory | MEMORY | Pattern storage, semantic retrieval |
| Human Review | HUMAN_REVIEW | Analyst feedback, accuracy tracking |
| Monitoring | MONITORING | Heartbeat, error rate, p99 anomaly detection |
| Compliance | L1/L2 | Delegated to statistical + GNN layers |

## Project Structure

```
payshield/
├── api/              FastAPI routes, schemas, dependencies
├── engine/           Statistical filter, GNN model, ensemble fusion
├── llm/              Ollama client, prompts, evidence collector, parser
├── tasks/            Celery worker, app, investigation task
├── agents/           Multi-agent framework (base, message, state, 8 agents)
├── store/            Redis client, velocity, device index, baselines, feature registry, graph DB
├── ml/               GNN model (PyG), trainer, registry, explainer, SHAP
├── data/             Synthetic data generators, graph builder, feature engineering
├── observability/    Prometheus metrics, structured logging, drift detection
├── dashboard/        React + TypeScript ops dashboard
├── models/           Calibrator, trained artifacts, model cards
├── configs/          YAML configs with per-environment thresholds
├── docker/           Docker Compose + Dockerfiles
├── scripts/          Training, evaluation, benchmarks, backtesting
└── tests/            Unit, integration, and load test suites
```

## API Surface

| Method | Endpoint | Description | Latency Target |
|--------|----------|-------------|---------------|
| `POST` | `/v1/score` | Single transaction fraud score + ensemble decision | p50 < 30 ms |
| `POST` | `/v1/batch` | Batch score up to 100 transactions | p50 < 200 ms |
| `GET` | `/v1/health` | Dependency health (Redis, model, Ollama, agents) | < 10 ms |
| `GET` | `/v1/metrics` | Prometheus metrics endpoint | < 10 ms |
| `WS` | `/v1/stream` | WebSocket push for high-risk alerts | Async |
| `GET` | `/v1/investigation/{txn_id}` | Retrieve LLM-generated narrative | < 100 ms |
| `POST` | `/v1/feedback` | Analyst feedback on false positive/negative | < 50 ms |
| `GET` | `/v1/agents/health` | All 8 agent statuses and metrics | < 50 ms |

## Key Technical Decisions

- **PyTorch Geometric (HeteroConv):** Native heterogeneous graph support for UPI's multi-entity structure
- **Ollama + Llama 3.1:** On-premises LLM for PCI-DSS / RBI data localization compliance
- **Redis sorted-sets:** O(log n) sliding window velocity checks at 100K+ TPS
- **Celery async queue:** Decouples 5-30s LLM generation from < 100 ms scoring hot path
- **Isotonic regression calibration:** Non-parametric calibration that preserves ranking
- **Jinja2 prompt templates:** Version-controlled, testable, with 3-shot examples
- **Bag-of-words MemoryAgent:** Zero-dependency pattern retrieval with keyword indexing

## Quick Start

```bash
# Start all services
docker compose -f docker/docker-compose.yml up

# Or run locally
pip install -r requirements.txt
python -m uvicorn api.main:app --reload

# Pull LLM model (first time)
python scripts/pull_ollama_model.py

# Train GNN model
python scripts/train_gnn.py

# Run benchmarks
python scripts/benchmark_ensemble.py
python scripts/benchmark_velocity_filter.py
```

## Project Status

PayShield v1.0.0 — **60-phase implementation complete** (2026-07-28)

| Phase | Focus | Status |
|-------|-------|--------|
| 1–10 | Foundation, graph schema, synthetic data, rule engine | ✅ |
| 11–20 | GNN, ML pipeline, LLM integration, drift detection | ✅ |
| 21–30 | Agent orchestration, training, inference, RBAC, prompt mgmt | ✅ |
| 31–40 | Agent Ops: ensemble fusion, LLM investigator, multi-agent, feedback, monitoring | ✅ |
| 41–50 | API factory, auth, scoring, investigation, WebSocket, DB, dashboard, tests | ✅ |
| 51–55 | K8s, DR, cost optimization, docs, release checklist | ✅ |
| 56–60 | SRE/chaos, A/B testing, advanced agents, compliance, final review | ✅ |

See [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md), [MAINTENANCE_ROADMAP.md](MAINTENANCE_ROADMAP.md), and [docs/](docs/) for comprehensive documentation.

## License

Internal — Hiring Portfolio
