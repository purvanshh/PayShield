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
| Layers | 3 | Hidden dimension 128, dropout 0.3 |
| Readout | Target-user readout + transaction attention + MLP | Per-sample target classification |
| Parameters | 371,843 | — |
| Train/Val/Test | 80/10/10 | User-disjoint split |
| Early stopping | 8 epochs | On validation PR-AUC |
| Optimizer | Adam | lr 4.3e-3 (Optuna-selected), weight decay 5e-4 |
| Schedule | Cosine annealing | — |
| Hyper-opt | 8-trial Optuna sweep `--sweep-trials 8` | Metric: val PR-AUC; hidden 32/64/128, layers 2/3, dropout 0/0.3/0.5, pos_weight 5/10/20, lr 1e-3..1e-2, batch 4/8/16 |

### Model Deployment

```bash
# 1. Retrain + gate against the currently promoted model (auto-registers only
#    when PR-AUC improves by >= 0.005)
make retrain

# 2. Or run the canonical benchmark and check the gate manually
make retrain-gate           # exit 0 = candidate beats production

# 3. Promote a model version (manual path, or via the retrain gate)
POST /admin/models/promote  { "version": "v1.1.0", "stage": "production" }

# 4. Inspect the currently promoted version
GET /admin/models/current   # → models/registry/latest metadata

# 5. The API picks up the new model on restart
#    (checkpoint metadata drives hidden/layers/dropout — no rebuild needed)

# 6. Verify L2 status distribution in Prometheus
layer2_escalation_total{status="SUCCESS"}  # should be > 0 after promotion
```

### Model Monitoring

- **PSI drift**: `GET /admin/drift/psi` — daily comparison of feature distributions; monitored set comes from `configs/feature_registry.yaml` (`monitoring: true`, `drift_key` aliases) with `skew_detection.min_samples = 100`; binary features use exact-value binning
- **L2 status**: Prometheus `layer2_escalation_total` by status (SUCCESS/SKIPPED/TIMEOUT/ERROR/MODEL_UNAVAILABLE)
- **Calibration**: ECE tracked; re-fit if ECE > 0.02
- **Fairness**: Re-run `models/fairness_audit.py` after retraining; check SPD/EOD thresholds (< 0.15)

## Feature Engineering

### Feature Categories (computed live per request)

| Category | Features | Source |
|----------|----------|--------|
| Velocity | Txn count (5 min, 1 hr, 24 hr), amount total, inter-arrival gap | Redis `velocity:user:*`, `velocity:dev:*` |
| Geo | Haversine distance from last-known location, geo-velocity | Redis `velocity:loc:*` |
| Merchant | Shell-company flag, round-amount share | Redis `FeatureCache` counters (`round_stats`, `merchant:{id}:round`) |
| Benford | Chi-squared on first digit, digit pair distribution | In-memory |
| Graph (L2) | Ego-graph node count, edge count, neighbor risk scores | `engine/graph_feature_engine.py` |

## Model Performance

| Metric | GNN v1.1.0 | GNN v1.0.0 | Edge-free MLP | Lift vs MLP |
|--------|-----------|-----------|---------------|-------------|
| PR-AUC | 0.4125 | 0.198 | 0.1028 | 4.0× |
| AUC-ROC | 0.7668 | 0.692 | 0.5395 | +0.23 |
| FPR @ 90% recall | 0.4877 | 0.71 | 0.8196 | −0.33 |
| Inference (CPU) | p50 0.60 ms / p99 0.70 ms | p99 2.5 ms | — | — |
| Graph schema | 4 node types, 5 edge types | — | — | — |

Source: `models/gnn_benchmark_results.json`
