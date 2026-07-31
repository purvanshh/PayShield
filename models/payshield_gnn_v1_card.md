# Model Card: PayShield GNN v1.0

## Model Details
- **Model Name:** PayShield Heterogeneous Graph Neural Network
- **Version:** 1.0.0
- **Type:** HeteroConv GraphSAGE with MLP classifier
- **Framework:** PyTorch Geometric 2.5+
- **Date:** July 22, 2026
- **Authors:** Purvansh Sahu

## Intended Use
- Real-time fraud scoring of UPI transactions (P2P, P2M, COLLECT)
- Detection of mule account rings, velocity burst attacks, merchant collusion, and account takeover
- Sub-millisecond statistical pre-filter → GNN scoring → async LLM explanation pipeline

## Architecture
- **Layers:** 2-layer HeteroConv with SAGEConv per edge type
- **Hidden dim:** 64
- **Aggregation:** Mean
- **Readout:** Global mean pooling (user + transaction embeddings), 2-layer MLP
- **Parameters:** 53,826 (measured)
- **Inference:** p50 1.0 ms / p90 1.5 ms / p99 2.5 ms on CPU (per ego-graph, median 48 nodes) — measured by `scripts/benchmark_gnn.py`

## Training Data
- **Source:** Synthetic UPI transaction generator
- **Size:** 30,000 transactions (10,000 users, 1,000 merchants, 5% fraud, seed 42)
- **Ego-graphs:** 5,558 (target user + neighbors; 80/10/10 user-disjoint split)
- **Fraud ratio:** 5% (fraud patterns: mule rings, burst, collusion, ATO)
- **Time span:** 30-day window with diurnal patterns

## Performance (measured 2026-07-31)

PR-AUC is the lead metric — at fraud rates ~0.1% (and 5% here), AUC-ROC is
dominated by correctly ranking the legitimate majority; PR-AUC measures the
minority (fraud) class directly.

| Metric | GNN | Edge-free MLP baseline | Lift |
|--------|-----|------------------------|------|
| **Test PR-AUC (lead)** | **0.198** | 0.056 | **3.5×** |
| Test AUC-ROC | 0.692 | 0.481 | +0.21 |
| FPR @ 90% recall | 0.71 | 0.91 | −0.20 |
| Inference p50 / p90 / p99 (CPU) | 1.0 / 1.5 / 2.5 ms | — | — |

Provenance: `python scripts/benchmark_gnn.py` → `models/gnn_benchmark_results.json`.
⚠️ This card previously claimed "AUC-ROC > 0.92" — that number was never measured and is replaced by the values above.

## Features
**User (5):** credit_score, account_age_days, kyc_tier, avg_monthly_txn_count, device_count
**Merchant (19):** category_code (15 MCC one-hot), avg_txn_amount, refund_rate, account_age_days, city_tier
**Device (4):** os_family, app_version (major, minor), is_emulator
**Transaction (4):** amount, hour-of-day, is_weekend, salary-day proxy
**Edge types:** performed, to, used, transferred_to, shared_by

## Limitations
- Trained on synthetic data; real-world UPI patterns may differ
- GNN performance degrades on cold-start users (< 5 historical transactions)
- Device fingerprint sharing signals assume honest fingerprint collection
- LLM investigator is asynchronous and not on the scoring hot path

## Fairness Considerations
- Demographic proxies (city tier, income tier) are not used as model features
- Credit score distributions reflect synthetic population, not real KYC data
- Model card to be updated before production deployment with real-world fairness audit
