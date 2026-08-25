"""Synthetic return-risk dataset generator for the XGBoost training pipeline.

This is the data engine behind ``scripts/train_xgb_return_risk.py``,
``scripts/ablation_study.py`` and ``scripts/tune_xgb.py``. It is separate
from ``return_generator.py`` (which feeds the Redis-backed live scorer)
because the offline model pipeline needs a *single flat table* of scored
orders with exactly the seven features the model consumes, plus a ground
truth label, with a well-posed (learnable, no-leakage) data-generating
process.

How it works
------------
Each order's ``returned`` outcome is drawn from a noisy logistic function of
the seven *visible* features **plus hidden features the model never observes**
(product rating, delivery speed, packaging quality, weather delays, customer
mood) **plus** irreducible label noise. This deliberately breaks a circular
data-generating process: the label is not a deterministic function of the
features XGBoost trains on, so the model must learn from noisy, incomplete
signal - exactly the situation a real merchant's data presents. The hidden
variables are stored on the frame as ``hidden_*`` columns (transparency) but
are excluded from ``FEATURES``.

- ``user_return_rate_30d`` / ``user_return_rate_90d`` are noisy estimates of
  the user's recent return propensity (a real deployment would compute these
  from rolling history; here we sample them so the two windows carry distinct
  signal - the 30d window is spikier, the 90d window is a cleaner estimate).
- ``category_return_baseline`` mirrors ``return_risk.feature_engine.CATEGORY_BASELINES``
  so the offline table and the production feature store agree on its meaning.
- The category baselines and payment/device/amount/recency features each carry
  a controlled, non-redundant share of the *visible* label signal, which is
  what makes the ablation study meaningful.

The single entry point ``generate_return_risk_dataset`` returns a
``pandas.DataFrame`` with columns:

- ``user_id``, ``merchant_id``, ``order_id``, ``user_type``, ``category``
- ``amount`` (INR), ``payment_method``, ``timestamp`` (datetime)
- ``returned`` (0/1 label)
- the seven model features:
  ``user_return_rate_30d``, ``user_return_rate_90d``,
  ``amount_vs_user_aov_ratio``, ``category_return_baseline``,
  ``payment_method_risk``, ``device_fingerprint_match``,
  ``days_since_last_order``
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

# The exact feature surface consumed by the XGBoost model. Kept in this
# module (not the scorer) so training, ablation and tuning all agree.
FEATURES = [
    "user_return_rate_30d",
    "user_return_rate_90d",
    "amount_vs_user_aov_ratio",
    "category_return_baseline",
    "payment_method_risk",
    "device_fingerprint_match",
    "days_since_last_order",
]

# Category baselines mirror return_risk.feature_engine.CATEGORY_BASELINES.
CATEGORY_BASELINES = {
    "fashion": 0.32,
    "electronics": 0.12,
    "groceries": 0.04,
    "home": 0.18,
    "beauty": 0.15,
    "sports": 0.20,
    "footwear": 0.25,
    "furniture": 0.055,
    "default": 0.15,
}

# Category sampling popularity (higher = ordered more often).
_CATEGORY_WEIGHTS = {
    "fashion": 3.0,
    "electronics": 2.0,
    "groceries": 1.5,
    "home": 1.2,
    "beauty": 1.2,
    "sports": 1.0,
    "footwear": 1.0,
    "furniture": 0.6,
}

# Payment methods and their return-risk (COD is highest: no money exchanged
# at checkout -> returns/RTO dominate). Mirrors the production mapping.
PAYMENT_RISK = {
    "UPI": 0.20,
    "CARD": 0.30,
    "WALLET": 0.40,
    "NETBANKING": 0.35,
    "COD": 1.00,
}

COD_SHARE = 0.255  # Amazon India COD share of payments

# Population average order value (Amazon India 2025 AOV ~Rs 74.5k). Used as
# the AOV denominator fallback at inference; the generator uses per-user AOV.
POPULATION_AOV = 74_500.0

DEFAULT_DAYS_SINCE_LAST_ORDER = 60  # new-user default (matches production)

# User archetypes (reuse the return_generator research: five archetypes,
# Indian e-commerce order cadence and value).
USER_TYPES = {
    "honest": {"return_rate_mean": 0.15, "return_rate_std": 0.04, "aov": 65000,
               "device_mean": 0.92, "device_std": 0.03},
    "casual_returner": {"return_rate_mean": 0.28, "return_rate_std": 0.05, "aov": 72000,
                        "device_mean": 0.85, "device_std": 0.06},
    "serial_returner": {"return_rate_mean": 0.48, "return_rate_std": 0.08, "aov": 80000,
                        "device_mean": 0.62, "device_std": 0.12},
    "fraud_returner": {"return_rate_mean": 0.62, "return_rate_std": 0.08, "aov": 88000,
                       "device_mean": 0.35, "device_std": 0.12},
    "new_user": {"return_rate_mean": 0.24, "return_rate_std": 0.10, "aov": 40000,
                 "device_mean": 0.55, "device_std": 0.15},
}

# Monthly seasonality (Amazon India 2025) reused from return_generator.
_MONTHLY_COUNTS = {
    "January": 1276, "February": 1183, "March": 1226, "April": 1203,
    "May": 1267, "June": 1225, "July": 1306, "August": 1312,
    "September": 1248, "October": 1233, "November": 1225, "December": 1296,
}
_SEASONALITY = [c / sum(_MONTHLY_COUNTS.values()) for c in _MONTHLY_COUNTS.values()]

# Noise on the two rate features. The 30d window is deliberately spikier than
# the 90d window so the two features are correlated but carry distinct signal.
RATE30_NOISE = 0.16
RATE90_NOISE = 0.06

# Hidden features: variables that genuinely influence whether an order is
# returned but that the model never observes. This breaks the "circular"
# data-generating process (where the label was a logistic of exactly the
# features the model trains on) and forces XGBoost to learn from noisy,
# incomplete signal - closer to real merchant data where you do not observe
# every variable. Ranges are (min, max).
HIDDEN_FEATURES = {
    "product_rating": (1.0, 5.0),      # 1-5 stars; lower rating -> higher return risk
    "delivery_speed_days": (1.0, 7.0),  # slower delivery -> higher return risk
    "packaging_quality": (1.0, 5.0),   # poorer packaging -> higher return risk
    "weather_delay": (0.0, 1.0),       # 1 if monsoon/festive logistics delay
    "customer_mood": (-1.0, 1.0),      # random sentiment factor
}

# Relative weight of each hidden feature in the label (see _hidden_logit).
HIDDEN_WEIGHTS = {
    "product_rating": 0.25,
    "delivery_speed_days": 0.15,
    "packaging_quality": 0.10,
    "weather_delay": 0.10,
    "customer_mood": 0.05,
}

# Scales the hidden signal so it is comparable to (not dwarfed by) the visible
# signal. Chosen by calibration: with HIDDEN_SCALE = 26 the hidden term carries
# enough label variance that the model learns from genuinely noisy, incomplete
# signal and the achievable (visible-features-only) PR-AUC settles near ~0.78.
HIDDEN_SCALE = 26.0

# Fraction of orders affected by a weather/festive logistics delay.
WEATHER_DELAY_RATE = 0.15

# Label noise (logit units).
LABEL_NOISE_STD = 0.10

# Expected value of _hidden_logit() over the feature distributions (0.25*0.5 +
# 0.15*0.5 + 0.10*0.5 + 0.10*0.15 + 0.05*0). Subtracted so the hidden signal
# adds variance (confounding) without shifting the base rate.
HIDDEN_MEAN = 0.265


def _logit_weights() -> dict[str, float]:
    """True data-generating weights (kept here for provenance).

    The main effects are linear-in-log-odds, but a few *interactions* are
    deliberately included so the problem is not perfectly linear: a model
    that captures interactions (XGBoost) can outperform a linear/weighted
    scorer. The interactions encode real domain knowledge:

    - ``COD + elevated recent return rate`` compounds (return-prone user on
      a no-money-at-checkout order is much riskier).
    - ``high value + unknown device`` compounds (expensive order, weak
      identity).
    - ``elevated 90d rate in a high-baseline category`` compounds.
    """
    return {
        "intercept": -4.60,
        "user_return_rate_30d": 3.60,
        "user_return_rate_90d": 1.80,
        "amount_vs_user_aov_ratio": 1.60,
        "category_return_baseline": 3.20,
        "payment_method_risk": 2.20,
        "device_fingerprint_match": -2.40,
        "days_since_last_order": 1.30,
        "latent": 2.80,
        "inter_30d_x_payment": 5.00,
        "inter_amount_x_device_risk": 4.00,
        "inter_90d_x_category": 3.20,
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _hidden_features(rng: random.Random) -> dict[str, float]:
    """Draw the unobservable per-order variables.

    Drawn independently of the visible features (they are genuine confounders:
    correlated with the label but not with what the model can see). They are
    stored on the DataFrame as ``hidden_*`` columns for transparency but are
    deliberately excluded from ``FEATURES``.
    """
    return {
        "product_rating": round(rng.uniform(*HIDDEN_FEATURES["product_rating"]), 1),
        "delivery_speed_days": round(rng.uniform(*HIDDEN_FEATURES["delivery_speed_days"]), 1),
        "packaging_quality": round(rng.uniform(*HIDDEN_FEATURES["packaging_quality"]), 1),
        "weather_delay": float(rng.random() < WEATHER_DELAY_RATE),
        "customer_mood": round(rng.uniform(*HIDDEN_FEATURES["customer_mood"]), 2),
    }


def _hidden_logit(hidden: dict[str, float]) -> float:
    """Hidden-feature contribution to the return logit (higher = more risk).

    Mirrors the semantics in HIDDEN_WEIGHTS: low product rating, slow
    delivery, poor packaging and a weather delay all push the return
    probability up; customer mood adds a small random nudge.
    """
    hw = HIDDEN_WEIGHTS
    score = 0.0
    score += hw["product_rating"] * (5.0 - hidden["product_rating"]) / 4.0
    score += hw["delivery_speed_days"] * (hidden["delivery_speed_days"] - 1.0) / 6.0
    score += hw["packaging_quality"] * (5.0 - hidden["packaging_quality"]) / 4.0
    score += hw["weather_delay"] * hidden["weather_delay"]
    score += hw["customer_mood"] * hidden["customer_mood"]
    return score


def _return_probability(
    features: dict[str, float],
    latent: float,
    hidden: dict[str, float],
    noise: float = 0.0,
) -> float:
    """P(return) for an order given visible + hidden features and label noise.

    The label is driven by the *visible* feature surface the model trains on
    (interactions included) **plus** the hidden features the model never sees,
    **plus** irreducible noise. XGBoost therefore learns from noisy, incomplete
    signal - the achievable PR-AUC is bounded by how much of the label variance
    the visible features can explain.
    """
    w = _logit_weights()
    logit = w["intercept"]
    logit += w["user_return_rate_30d"] * features["user_return_rate_30d"]
    logit += w["user_return_rate_90d"] * features["user_return_rate_90d"]
    logit += w["amount_vs_user_aov_ratio"] * math.log(features["amount_vs_user_aov_ratio"])
    logit += w["category_return_baseline"] * features["category_return_baseline"]
    logit += w["payment_method_risk"] * features["payment_method_risk"]
    logit += w["device_fingerprint_match"] * features["device_fingerprint_match"]
    logit += w["days_since_last_order"] * min(features["days_since_last_order"] / 45.0, 1.0)
    logit += w["latent"] * (latent - 0.30)
    # Non-linear interactions (see _logit_weights docstring).
    logit += w["inter_30d_x_payment"] * features["user_return_rate_30d"] * features["payment_method_risk"]
    logit += (
        w["inter_amount_x_device_risk"]
        * max(features["amount_vs_user_aov_ratio"] - 1.0, 0.0)
        * (1.0 - features["device_fingerprint_match"])
    )
    logit += w["inter_90d_x_category"] * features["user_return_rate_90d"] * features["category_return_baseline"]
    # Hidden (unobserved) signal + noise. Centred on zero so it adds
    # confounding variance without shifting the base rate.
    logit += HIDDEN_SCALE * (_hidden_logit(hidden) - HIDDEN_MEAN)
    logit += noise
    return 1.0 / (1.0 + math.exp(-logit))


def _seasonal_dates(num_orders: int, start: datetime, rng: random.Random) -> list[datetime]:
    """Draw ``num_orders`` dates weighted by Amazon monthly seasonality."""
    base = start.year * 12 + start.month - 1
    dates: list[datetime] = []
    for _ in range(num_orders):
        month_idx = rng.choices(range(12), weights=_SEASONALITY)[0]
        year, month = divmod(base + month_idx, 12)
        day = rng.randint(1, 28)
        dates.append(datetime(year, month + 1, day, rng.randint(8, 22), rng.randint(0, 59)))
    dates.sort()
    return dates


def _device_fingerprint_match(rng: random.Random, archetype: dict[str, Any]) -> float:
    return _clamp(rng.gauss(archetype["device_mean"], archetype["device_std"]), 0.05, 0.99)


def _payment_method(rng: random.Random) -> str:
    if rng.random() < COD_SHARE:
        return "COD"
    return rng.choices(
        ["UPI", "CARD", "WALLET", "NETBANKING"], weights=[0.55, 0.25, 0.10, 0.10]
    )[0]


def _days_since_last_order(np_rng: np.random.Generator) -> float:
    """Draw an inter-order gap (days). Log-normal around ~12 days, capped at 60."""
    return float(min(np_rng.exponential(12.0), DEFAULT_DAYS_SINCE_LAST_ORDER))


def generate_return_risk_dataset(
    n_orders: int = 10000,
    seed: int = 42,
    orders_per_user: int = 20,
    window_days: int = 365,
) -> pd.DataFrame:
    """Generate a flat table of scored orders with the seven model features.

    Parameters mirror the pipeline defaults so the scripts are one-liners:
    ``n_orders`` total orders, ``seed`` for reproducibility, ``orders_per_user``
    orders per user (so each user has a real chronological history for the
    60/20/20 per-user split), ``window_days`` history horizon.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    user_types = list(USER_TYPES.keys())
    users_per_type = max(10, round(n_orders / (orders_per_user * len(user_types))))

    end = datetime.utcnow() - timedelta(days=7)
    start = end - timedelta(days=window_days)

    categories = [c for c in CATEGORY_BASELINES if c != "default"]
    cat_weights = [_CATEGORY_WEIGHTS[c] for c in categories]

    rows: list[dict[str, Any]] = []
    user_counter = 0
    for utype in user_types:
        archetype = USER_TYPES[utype]
        for _ in range(users_per_type):
            user_counter += 1
            user_id = f"U_{user_counter:04d}"
            latent = _clamp(rng.gauss(archetype["return_rate_mean"], archetype["return_rate_std"]), 0.02, 0.85)
            aov = archetype["aov"]
            merchant_id = f"M_{utype}"

            dates = _seasonal_dates(orders_per_user, start, rng)

            for i, ts in enumerate(dates):
                # Visible features are generated before the label (no leakage).
                rate_30d = _clamp(latent + rng.gauss(0.0, RATE30_NOISE), 0.02, 0.90)
                rate_90d = _clamp(latent + rng.gauss(0.0, RATE90_NOISE), 0.02, 0.90)
                aov_ratio = _clamp(math.exp(rng.gauss(0.0, 0.5)), 0.15, 4.0)
                amount = aov * aov_ratio
                category = rng.choices(categories, weights=cat_weights)[0]
                payment_method = _payment_method(rng)
                device_match = _device_fingerprint_match(rng, archetype)
                days_since = _days_since_last_order(np_rng)
                hidden = _hidden_features(rng)

                features = {
                    "user_return_rate_30d": rate_30d,
                    "user_return_rate_90d": rate_90d,
                    "amount_vs_user_aov_ratio": aov_ratio,
                    "category_return_baseline": float(
                        CATEGORY_BASELINES.get(category, CATEGORY_BASELINES["default"])
                    ),
                    "payment_method_risk": float(PAYMENT_RISK[payment_method]),
                    "device_fingerprint_match": device_match,
                    "days_since_last_order": days_since,
                }

                label_noise = float(np_rng.normal(0.0, LABEL_NOISE_STD))
                p_return = _return_probability(features, latent, hidden, noise=label_noise)
                returned = 1 if np_rng.random() < p_return else 0

                rows.append(
                    {
                        "user_id": user_id,
                        "merchant_id": merchant_id,
                        "order_id": f"ORD_{user_id}_{i:03d}",
                        "user_type": utype,
                        "category": category,
                        "amount": round(amount, 2),
                        "payment_method": payment_method,
                        "timestamp": ts,
                        "returned": returned,
                        **features,
                        # Hidden variables kept for transparency/diagnostics but
                        # never part of FEATURES (the model does not see them).
                        **{f"hidden_{k}": v for k, v in hidden.items()},
                    }
                )

    df = pd.DataFrame(rows).head(n_orders).reset_index(drop=True)
    df.attrs["seed"] = seed
    return df


def base_rate(df: pd.DataFrame) -> float:
    """Fraction of orders labelled as returned."""
    return float(df["returned"].mean())


if __name__ == "__main__":
    d = generate_return_risk_dataset(n_orders=1000, seed=42)
    print(d.head())
    print(f"\nRows: {len(d)}  Base rate: {base_rate(d):.3f}")
    print("Feature means:\n", d[FEATURES].mean().round(3).to_string())
