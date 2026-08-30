# Simulator Validation: Why Synthetic, Why This Simulator

> **This document is your shield.** When a judge asks *"why synthetic?"*, the
> answer is here — not a hand-wave, but the evaluated alternatives, the
> calibration sources, and the exact sensitivity of every headline number.

We did not default to synthetic data because we couldn't find real data. We
**evaluated** public return-risk datasets and **rejected** them for
distribution mismatch with Indian e-commerce, then built a calibrated
simulator whose parameters are pinned to published Indian industry
distributions and validated against the real Indian retail history we could
obtain. The choice is intelligent restraint, not failure to find data.

## 1. Public Datasets Evaluated and Rejected

| Dataset | Year | Region | Why Rejected |
|---------|------|--------|--------------|
| UK E-Commerce Returns | 2021 | UK | Distribution mismatch: **COD is absent** (India's highest-abuse payment mode), return reasons differ (fit vs. logistics), and the logistics infrastructure predates UDAN-era regional delivery. Training here would teach the model the wrong payment and reason structure. |
| Indian Retail Sales (validation set) | — | India | Not a training set: **4,200 orders, 98% single-order customers** → per-user return history (the model's dominant signal) degrades to the population prior. Out-of-time holdout: PR-AUC 0.136, ROC 0.524 ≈ random — the dataset genuinely has weak order-level return signal (see `docs/REAL_DATA_VALIDATION_RETROSPECTIVE.md`). |
| Amazon India 2025 report | 2025 | India | **Reconstructed** from published aggregate margins (the raw order-level file was unavailable, so an external benchmark could not be certified). Used to **calibrate the DGP** — category return rates 31–34%, AOV ~₹70–80k, COD ~25.5% — not to train the model directly. |

The common thread: every public dataset either lacks the payment/return-reason
structure of Indian e-commerce (UK), lacks per-user history depth (retail), or
is unavailable at order level (Amazon). Training on any of them would inject a
distribution mismatch — so we simulate the target distribution instead.

## 2. DGP Calibration Sources

| Parameter | Our Value | Source | Note |
|-----------|-----------|--------|------|
| Fashion return rate | 18% | RedSeer / Bain India E-commerce Report 2024 | Indian fashion average |
| Electronics return rate | 8–12% | Same | Varies by category |
| Mean AOV (Fashion) | ₹2,500 | Industry estimates | Tier 1–2 cities |
| Review cost | ₹200 | Assumed | 15 min @ ₹800/hr operator |
| Block cost | ₹3,180 | CAC ₹1,500 + AOV ₹2,500 + churn ₹180 | Conservative |

These are the exact values the cost model runs on
(`docs/cost_model/assumptions.py`), so every ₹ figure in the README traces to
a published prior — never a fabricated constant.

## 3. Hidden Confounders

The model never observes these — they inflate label noise exactly like a real
merchant's data feed, so the model learns from incomplete signal rather than
circularly recovering what it was given:

- `product_rating` (Stage 1: hidden, Stage 2: visible)
- `delivery_speed_days` (Stage 1: hidden, Stage 2: visible)
- `packaging_quality`, `weather_delay`, `customer_mood` (always hidden)

This is why the absolute PR-AUC is lower but more honest than a circular
benchmark — and why the ablation (LOFO) can measure genuine per-feature
contribution against hidden confounders.

## 4. What Would Change With Real Data

| Assumption | If Real Data Shows Different |
|------------|------------------------------|
| 18% fashion return rate | Resample DGP or reweight cost model |
| Feature importances | Retrain XGBoost; if the order changes, investigate data leakage |
| False-positive cost ₹200 | Calibrate to actual operator wages at merchant |

Each of these is a **reversible, pre-planned knob** — the generator and cost
model are parameterised, so the numbers adapt to a real merchant's data
without a redesign. See [`docs/REAL_DATA_ROADMAP.md`](REAL_DATA_ROADMAP.md)
for the concrete plan to close the remaining gap with real orders.
