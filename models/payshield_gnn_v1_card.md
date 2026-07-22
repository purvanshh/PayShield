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
- **Parameters:** ~15K
- **Inference:** < 50 ms on CPU (2-hop ego graph, < 200 nodes)

## Training Data
- **Source:** Synthetic UPI transaction generator
- **Size:** 20,000 transactions (80/20 train/val split)
- **Users:** 2,000 with Indian demographic distributions
- **Merchants:** 1,000 across 15 MCC categories
- **Fraud ratio:** 5% (250 fraud patterns: mule rings, burst, collusion, ATO)
- **Time span:** 30-day window with diurnal patterns

## Performance
- **Validation AUC-ROC:** > 0.92
- **Validation PR-AUC:** > 0.85
- **False positive rate at 0.90 recall:** < 5%
- **p50 latency:** < 10 ms (Layer 1), < 30 ms (Layer 1 + Layer 2)
- **p99 latency:** < 100 ms end-to-end

## Features
**User:** credit_score, account_age_days, kyc_tier, avg_monthly_txn_count, device_count
**Merchant:** category_code, avg_txn_amount, refund_rate, account_age_days, benford_chi2
**Device:** os_family, app_version, is_emulator
**Transaction:** amount, timestamp
**Edge types:** performed, to, used, transfer, shared_by

## Limitations
- Trained on synthetic data; real-world UPI patterns may differ
- GNN performance degrades on cold-start users (< 5 historical transactions)
- Device fingerprint sharing signals assume honest fingerprint collection
- LLM investigator is asynchronous and not on the scoring hot path

## Fairness Considerations
- Demographic proxies (city tier, income tier) are not used as model features
- Credit score distributions reflect synthetic population, not real KYC data
- Model card to be updated before production deployment with real-world fairness audit
