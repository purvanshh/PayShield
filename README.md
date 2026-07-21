# PayShield

Real-Time UPI Fraud Detection & Graph-Powered Investigation

A production-grade fraud detection system purpose-built for India's UPI digital payment ecosystem. Combines statistical filtering, heterogeneous Graph Neural Networks, and LLM-powered investigation narratives in a unified inference pipeline.

## Architecture

- **Layer 1 — Statistical Filter:** Sub-millisecond deterministic rules (velocity, geo-velocity, Benford's Law)
- **Layer 2 — Graph Neural Network:** HeteroConv GraphSAGE scoring relational fraud patterns
- **Layer 3 — LLM Investigator:** Async narrative generation via local Llama 3.1

## Quick Start

```bash
docker compose -f docker/docker-compose.yml up
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/score` | Single transaction fraud score |
| POST | `/v1/batch` | Batch score up to 100 transactions |
| GET  | `/v1/health` | Dependency health check |
| GET  | `/v1/metrics` | Prometheus metrics |
| GET  | `/v1/investigation/{txn_id}` | LLM investigation narrative |
| POST | `/v1/feedback` | Analyst feedback |
