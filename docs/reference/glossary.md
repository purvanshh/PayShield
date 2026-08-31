# Glossary

| Term | Definition |
|------|------------|
| **AOV** | Average Order Value — the merchant's typical order size; `amount_vs_user_aov_ratio` compares an order against it |
| **Ablation** | Removing a feature and re-training to measure its unique contribution (see `scripts/ablation_study.py`) |
| **Base rate** | The population return rate before any scoring (e.g. ~42% on the calibrated synthetic vertical) |
| **COD** | Cash on Delivery — highest-return-risk payment method (no money exchanged at checkout) |
| **Confounder** | An unobserved variable that influences the label (product rating, delivery speed, …) — deliberately hidden in the synthetic DGP |
| **DGP** | Data-Generating Process — how synthetic return labels are produced |
| **Flag rate** | Fraction of orders the review gate flags |
| **Gate / review gate** | The score threshold above which an order is flagged (config-driven, e.g. 0.50) |
| **LOFO** | Leave-One-Feature-Out — the ablation method that retrains without each feature |
| **PR-AUC** | Precision-Recall Area Under Curve — ranking quality on the minority (return) class |
| **Precision** | Of the orders flagged, the fraction that were real returns |
| **Recall** | Of the real returns, the fraction that were flagged |
| **Return rate** | Fraction of orders returned (e.g. `user_return_rate_30d` = returns in the last 30 days / orders) |
| **Tier** | LOW / MEDIUM / HIGH — the merchant-facing action mapping (ship / review / require prepaid) |
| **XGBoost** | Gradient-boosted tree model — the primary scoring engine |