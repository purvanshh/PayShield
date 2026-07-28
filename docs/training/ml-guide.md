# ML Model Guide

## Model Training

### Training a New Model

```bash
# Prepare training data
python scripts/prepare_training_data.py --start-date 2026-01-01 --end-date 2026-06-30

# Train all models
python ml/training/train_pipeline.py --config configs/training.yaml

# Train single model
python ml/training/train_single.py --model xgboost --params configs/xgboost_params.json

# Evaluate model
python ml/training/evaluate.py --model-path models/v2/xgboost.pkl --test-data data/test.parquet
```

### Training Configuration

```yaml
# configs/training.yaml
training:
  test_size: 0.2
  validation_size: 0.1
  random_state: 42
  n_folds: 5

models:
  xgboost:
    params:
      n_estimators: 500
      max_depth: 8
      learning_rate: 0.01
      subsample: 0.8
      colsample_bytree: 0.8
      scale_pos_weight: 3.0

  lightgbm:
    params:
      n_estimators: 500
      num_leaves: 64
      learning_rate: 0.01
      feature_fraction: 0.8
      bagging_fraction: 0.8
      bagging_freq: 5
      class_weight: balanced

  catboost:
    params:
      iterations: 500
      depth: 8
      learning_rate: 0.01
      l2_leaf_reg: 3.0
      auto_class_weights: Balanced

  random_forest:
    params:
      n_estimators: 300
      max_depth: 16
      min_samples_split: 50
      min_samples_leaf: 20
      class_weight: balanced_subsample

  mlp:
    params:
      hidden_layer_sizes: [256, 128, 64]
      activation: relu
      solver: adam
      alpha: 0.0001
      batch_size: 256
      early_stopping: true
      max_iter: 200
```

## Model Evaluation

### Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| AUC-ROC | Area under ROC curve | > 0.95 |
| Precision | True positives / predicted positives | > 0.85 |
| Recall | True positives / actual positives | > 0.90 |
| F1 Score | Harmonic mean of precision & recall | > 0.87 |
| FPR | False positive rate | < 0.05 |

### Evaluation Report

```bash
python ml/training/evaluate.py --model-path models/v2/ensemble.pkl --report-format html
```

## Feature Engineering

### Feature Groups

| Group | Count | Examples |
|-------|-------|----------|
| Transaction | 25 | amount, currency, type, timestamp features |
| Merchant | 30 | category, country, volume, velocity |
| User | 45 | history, frequency, avg amount, behavioral |
| Device | 35 | fingerprint, IP, user-agent, geo |
| Network | 40 | ISP, ASN, proxy detection, reputation |
| Temporal | 30 | hour, day, season, holiday, rolling windows |

### Adding New Features

1. Add feature function in `ml/features/builder.py`
2. Register in `ml/features/registry.py`
3. Add to feature set in `configs/features.yaml`
4. Run feature importance analysis
5. Update model training pipeline

## Model Serving

### Loading Models

```python
from ml.models import ModelRegistry

registry = ModelRegistry()
model = registry.load("ensemble_v2")
result = model.predict(features)
```

### Model Versioning

- Models stored in S3: `s3://payshield-models/{name}/{version}/`
- Local cache: `models/cache/{name}_{version}.pkl`
- Version format: `v{major}.{minor}.{patch}`

### Hot-Reload

```python
# Models auto-detect new versions from S3
from ml.models import watch_for_updates
watch_for_updates(interval_seconds=300)
```

## A/B Testing

```yaml
# configs/ab_testing.yaml
experiments:
  - name: ensemble_v2_vs_v3
    variants:
      - name: control
        model: ensemble_v2
        traffic: 50
      - name: treatment
        model: ensemble_v3
        traffic: 50
    metrics:
      - precision
      - recall
      - latency_p99
    duration_hours: 72
```

## Online Learning

### Feedback Integration

```python
# Feedback loop from human reviews
from ml.online_learning import OnlineLearner

learner = OnlineLearner()
learner.process_feedback(transaction_id="txn_001", actual_label="fraud")
```

### Model Updates

- **Daily**: Incremental training on new labeled data
- **Weekly**: Full retraining with feature engineering
- **Monthly**: Architecture search and hyperparameter tuning
