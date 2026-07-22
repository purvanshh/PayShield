# PayShield — Real-Time UPI Fraud Detection & Graph-Powered Investigation

A production-grade fraud detection system purpose-built for **India's UPI digital payment ecosystem**. PayShield targets the specific attack vectors that dominate Indian fintech — mule account rings, velocity burst attacks, merchant collusion, and device-fingerprint reuse — by combining three detection modalities:

1. **Layer 1 (Statistical Filter):** Sub-millisecond deterministic rules (velocity z-score, geo-velocity impossibility, Benford's Law deviation)
2. **Layer 2 (Graph Neural Network):** Heterogeneous HeteroConv GraphSAGE that learns relational fraud patterns across users, merchants, devices, and transactions
3. **Layer 3 (LLM Investigator):** Async narrative generation via local Llama 3.1, translating model evidence into analyst-readable fraud reports

## Architecture

```
                          POST /score
                              │
                     ┌────────▼────────┐
                     │  L1 Statistical │  < 1 ms
                     │     Filter      │
                     └────────┬────────┘
                              │ (escalated only)
                     ┌────────▼────────┐
                     │  L2 GNN Scorer  │  < 50 ms
                     │  HeteroConv     │
                     └────────┬────────┘
                              │ (blocked txns)
                     ┌────────▼────────┐
                     │  L3 LLM Async   │  async
                     │  Investigator   │
                     └─────────────────┘
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

## Quick Start

```bash
# Start all services
docker compose -f docker/docker-compose.yml up

# Or run locally
pip install -r requirements.txt
python -m uvicorn api.main:app --reload
```

## API Surface

| Method | Endpoint | Description | Latency Target |
|--------|----------|-------------|---------------|
| `POST` | `/v1/score` | Single transaction fraud score | p50 < 30 ms |
| `POST` | `/v1/batch` | Batch score up to 100 transactions | p50 < 200 ms |
| `GET` | `/v1/health` | Dependency health (Redis, model) | < 10 ms |
| `GET` | `/v1/metrics` | Prometheus metrics endpoint | < 10 ms |
| `WS` | `/v1/stream` | WebSocket push for high-risk alerts | Async |
| `GET` | `/v1/investigation/{txn_id}` | Retrieve LLM-generated narrative | < 100 ms |
| `POST` | `/v1/feedback` | Analyst feedback on false positive/negative | < 50 ms |

## Project Structure

```
payshield/
├── api/              # FastAPI app, routes, schemas, dependencies
├── engine/           # Statistical filter, GNN model, ensemble, explainer
├── llm/              # LLM investigator, prompt templates, response cache
├── data/             # Synthetic data generator, graph builder, feature engineering
├── store/            # Redis client, feature store, graph database abstraction
├── observability/    # Prometheus metrics, structured logging, drift detection
├── dashboard/        # React + TypeScript ops dashboard
├── models/           # Trained model artifacts and model cards
├── configs/          # YAML configs with per-environment thresholds
├── docker/           # Docker Compose + Dockerfiles
├── scripts/          # Training, evaluation, benchmark, backtesting
└── tests/            # Unit, integration, and load test suites
```

## Fraud Detection Pipeline

### Layer 1 — Statistical Filter
- **Velocity anomalies:** z-score > 3 on 1h/24h transaction counts
- **Burst detection:** > 10 transactions in 5 minutes for low-frequency accounts
- **Amount deviation:** > 5x user's 30-day median with elevated velocity
- **Geo-impossible:** > 900 km/h between consecutive transactions
- **Benford's Law:** χ² > 15.51 on merchant first-digit distribution (n > 20)

### Layer 2 — Graph Neural Network
- **Node types:** User, Merchant, Device, Transaction
- **Edge types:** performed, to, used, transfer, shared_by
- **Model:** 2-layer HeteroConv GraphSAGE with mean aggregation
- **Readout:** Global mean pooling → 2-layer MLP → sigmoid

### Layer 3 — LLM Investigator (Async)
- **Model:** Llama 3.1 8B via Ollama (local, no API cost)
- **Input:** SHAP importances, GNNExplainer subgraph, velocity stats, Benford χ²
- **Output:** Structured JSON with narrative, fraud type, confidence, recommended action
- **Cache:** Redis-backed SHA-256 deduplication with 24h TTL

## Development Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundation: synthetic data, graph builder, stat filter, Redis store | ✅ |
| 2 | Graph ML Core: GNN model, training, ego-graph, explainer | ✅ |
| 3 | GenAI & API: FastAPI, LLM, Celery, Prometheus | ✅ |
| 4 | Dashboard & Polish: React UI, WebSocket, drift, model card | ✅ |
| 5 | Evaluation & Hardening: tests, backtesting, ablation, Docker | ✅ |

## License

Internal — Hiring Portfolio
