# ML Model Guide

## GNN Model Training

### Training the Graph Neural Network

```bash
# Generate synthetic training data
python scripts/generate_synthetic_data.py --users 10000 --merchants 1000 --transactions 30000 --fraud-ratio 0.05

# Train the GNN
python scripts/train_gnn.py --epochs 60 --early-stopping 10 --lr 0.001

# Benchmark against edge-free MLP baseline
python scripts/benchmark_gnn.py

# Results are written to models/gnn_benchmark_results.json
```

### Calibration Pipeline

```bash
# Fit isotonic calibrator on validation predictions
# (handled by engine/ensemble.py during training)
python -c "
from engine.ensemble import ConfidenceCalibrator
from models.gnn_benchmark_results import validation_scores, validation_labels
calibrator = ConfidenceCalibrator()
calibrator.fit(validation_scores, validation_labels)
calibrator.save('models/production/calibrator_v1.pkl')
"
```

Post-fitting: ECE 0.055 → 0.010.

### Model Card Generation

```bash
# Auto-generate from benchmark JSON (zero hand-edited metrics)
python scripts/generate_model_card.py
# → models/payshield_gnn_v1_card.md
```

### Fairness Audit

```bash
# Compute SPD/EOD on synthetic demographic slices
python models/fairness_audit.py
```

### Training Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| Architecture | HeteroConv + SAGEConv (mean aggr) | Per-edge-type weight matrices |
| Layers | 2 | Hidden dimension 64 |
| Readout | Global mean pool + MLP | Graph-level classification |
| Parameters | 53,826 | — |
| Train/Val/Test | 80/10/10 | User-disjoint split |
| Early stopping | 10 epochs | On validation PR-AUC |
| Optimizer | Adam | lr 0.001, weight decay 1e-5 |
| Schedule | Cosine annealing | — |
| Training time | ~90 s | Synthetic data, CPU |

### Model Deployment

```bash
# 1. Promote a model version
POST /admin/models/promote  { "version": "v0.2.0" }

# 2. The API picks up the new model on restart
#    (hot-reload not implemented — requires restart)

# 3. Verify L2 status distribution in Prometheus
layer2_escalation_total{status="SUCCESS"}  # should be > 0 after promotion
```

### Model Monitoring

- **PSI drift**: `GET /admin/drift/psi` — daily comparison of feature distributions
- **L2 status**: Prometheus `layer2_escalation_total` by status (SUCCESS/SKIPPED/TIMEOUT/ERROR/MODEL_UNAVAILABLE)
- **Calibration**: ECE tracked; re-fit if ECE > 0.02
- **Fairness**: Re-run `models/fairness_audit.py` after retraining; check SPD/EOD thresholds (< 0.15)

## Feature Engineering

### Feature Categories (computed live per request)

| Category | Features | Source |
|----------|----------|--------|
| Velocity | Txn count (5 min, 1 hr, 24 hr), amount total | Redis `velocity:user:*`, `velocity:dev:*` |
| Geo | Haversine distance, geo-velocity, device consistency | Redis `velocity:loc:*` |
| Benford | Chi-squared on first digit, digit pair distribution | In-memory |
| Graph (L2) | Ego-graph node count, edge count, neighbor risk scores | `engine/graph_feature_engine.py` |

## Model Performance

| Metric | GNN | Edge-free MLP | Lift |
|--------|-----|---------------|------|
| PR-AUC | 0.195 | 0.052 | 3.8× |
| AUC-ROC | 0.667 | 0.442 | +0.225 |
| FPR @ 90% recall | 0.714 | 0.958 | −0.244 |
| Inference (CPU) | p99 0.43 ms | — | — |
| Graph schema | 4 node types, 5 edge types | — | — |

Source: `models/gnn_benchmark_results.json`
