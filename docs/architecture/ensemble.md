# Ensemble Architecture

## Model Overview

The PayShield ensemble consists of 5 base models and 1 meta-learner:

| Model | Type | Purpose | Weight |
|-------|------|---------|--------|
| XGBoost | Gradient Boosted Trees | General fraud patterns | 0.25 |
| LightGBM | Gradient Boosted Trees | High-cardinality features | 0.25 |
| CatBoost | Gradient Boosted Trees | Categorical features | 0.20 |
| RandomForest | Bagged Trees | Robust baseline | 0.15 |
| MLP | Neural Network | Complex interactions | 0.15 |
| **Meta-Learner** | Gradient Boosting | Calibrated final output | — |

## Fusion Strategy

### Weighted Voting
```
final_score = Σ(weight_i * model_i_confidence)
```

### Confidence Thresholds
| Threshold | Action |
|-----------|--------|
| ≥ 0.9 | Auto-approve (no investigation) |
| 0.7 – 0.9 | Send to LLM investigator |
| 0.5 – 0.7 | Send to agent orchestrator |
| < 0.5 | Auto-decline (high confidence fraud) |

## Training Pipeline

### Offline Training
1. Feature engineering on historical transactions
2. Train each base model independently
3. Train meta-learner on cross-validation predictions
4. Evaluate against holdout set
5. Version and register model

### Online Learning
- Daily incremental training on new labeled data
- Feedback incorporation within 1 hour
- Automatic model rollback if metrics degrade

## Feature Engineering

### Feature Categories
- **Transaction**: amount, currency, timestamp, type
- **Merchant**: category, location, age, volume
- **User**: history, velocity, behavioral profile
- **Device**: fingerprint, browser, OS, IP reputation
- **Network**: geolocation, VPN/proxy detection, ASN

### Pipeline
```
Raw Transaction → Validation → Cleaning → Transformation → Selection → Feature Vector
```

## Model Hosting

- Models stored in S3 with versioning
- Cached locally with LRU eviction
- Hot-reload on new version detection
- Fallback to previous version on failure
