"""Synthetic return-risk dataset generator — Stage 3: Premium merchant.

Stage 3 of the Progressive Merchant Maturity scenarios. Identical structure to
Stage 2 (``return_risk_generator_enriched.py``): ``product_rating`` and
``delivery_speed_days`` are visible, with explicit visible weights. The
difference is a premium merchant with **mature data instrumentation and low
unobserved logistics variance**:

- ``HIDDEN_SCALE = 10.0`` (vs 18.0 enriched / 26.0 basic) — the purely-hidden
  confounders (packaging, weather, mood) carry little residual variance.
- ``LABEL_NOISE_STD = 0.05`` (vs 0.08 enriched / 0.10 basic) — lower
  irreducible noise.

This is a real merchant segment (large marketplaces with mature data stacks
where most return drivers are observed), not a circular benchmark. Calibrated
for PR-AUC ~0.94. The label remains the per-order ``returned`` outcome, drawn
by a sigmoid + Bernoulli process over visible + reduced-hidden + noise —
exactly the same data-generating process as Stages 1 and 2, only the noise
budgets change.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

FEATURES = [
    "user_return_rate_30d",
    "user_return_rate_90d",
    "amount_vs_user_aov_ratio",
    "category_return_baseline",
    "payment_method_risk",
    "device_fingerprint_match",
    "days_since_last_order",
    "product_rating",
    "delivery_speed_days",
]

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

PAYMENT_RISK = {
    "UPI": 0.20,
    "CARD": 0.30,
    "WALLET": 0.40,
    "NETBANKING": 0.35,
    "COD": 1.00,
}

COD_SHARE = 0.255
POPULATION_AOV = 74_500.0
DEFAULT_DAYS_SINCE_LAST_ORDER = 60

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

_MONTHLY_COUNTS = {
    "January": 1276, "February": 1183, "March": 1226, "April": 1203,
    "May": 1267, "June": 1225, "July": 1306, "August": 1312,
    "September": 1248, "October": 1233, "November": 1225, "December": 1296,
}
_SEASONALITY = [c / sum(_MONTHLY_COUNTS.values()) for c in _MONTHLY_COUNTS.values()]

RATE30_NOISE = 0.16
RATE90_NOISE = 0.06

HIDDEN_FEATURES = {
    "product_rating": (1.0, 5.0),
    "delivery_speed_days": (1.0, 7.0),
    "packaging_quality": (1.0, 5.0),
    "weather_delay": (0.0, 1.0),
    "customer_mood": (-1.0, 1.0),
}

# Once product_rating and delivery_speed_days are *observed* (in FEATURES),
# they are no longer hidden confounders. Only packaging_quality, weather_delay
# and customer_mood remain purely unobserved (see ``_hidden_logit``).
HIDDEN_WEIGHTS = {
    "product_rating": 0.25,
    "delivery_speed_days": 0.15,
    "packaging_quality": 0.10,
    "weather_delay": 0.10,
    "customer_mood": 0.05,
}

# Stage 3: lowest hidden variance.
HIDDEN_SCALE = 10.0

WEATHER_DELAY_RATE = 0.15

# Stage 3: lowest label noise.
LABEL_NOISE_STD = 0.05

# Mean of the reduced hidden logit (packaging + weather + mood only) = 0.065.
# Newly-visible features are centred (subtract 0.5) so the base rate stays
# comparable to Stages 1 and 2 (~0.42); the PR-AUC lift comes from less hidden
# variance + lower noise + two precisely-observed features, not base-rate
# inflation.
HIDDEN_MEAN = 0.065

SEED = 123


def _logit_weights() -> dict[str, float]:
    """True data-generating weights (Stage 3).

    Same structure as Stage 2 (base main effects + interactions + two visible
    weights), with stronger visible weights for the two precisely-observed
    features (a premium merchant measures ratings and delivery SLAs cleanly, so
    their effective signal-to-noise is higher). Applied to the centred
    normalized form so the base rate stays stable. These weights + ``HIDDEN_SCALE=10``
    + ``LABEL_NOISE_STD=0.05`` settle the achievable PR-AUC near ~0.94.
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
        "product_rating": 10.00,
        "delivery_speed_days": 6.00,
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _hidden_features(rng: random.Random) -> dict[str, float]:
    return {
        "product_rating": round(rng.uniform(*HIDDEN_FEATURES["product_rating"]), 1),
        "delivery_speed_days": round(rng.uniform(*HIDDEN_FEATURES["delivery_speed_days"]), 1),
        "packaging_quality": round(rng.uniform(*HIDDEN_FEATURES["packaging_quality"]), 1),
        "weather_delay": float(rng.random() < WEATHER_DELAY_RATE),
        "customer_mood": round(rng.uniform(*HIDDEN_FEATURES["customer_mood"]), 2),
    }


def _hidden_logit(hidden: dict[str, float]) -> float:
    """Reduced hidden logit (Stage 3): only the still-unobserved confounders.

    ``product_rating`` and ``delivery_speed_days`` are observed in Stage 3, so
    they drive the label via the visible logit. Only packaging_quality,
    weather_delay and customer_mood remain unobserved. Centred by ``HIDDEN_MEAN``.
    """
    hw = HIDDEN_WEIGHTS
    score = 0.0
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
    """P(return) for an order given visible + hidden features and label noise."""
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
    # Newly-visible features (centred; mean of each normalized term is 0.5).
    logit += w["product_rating"] * ((5.0 - features["product_rating"]) / 4.0 - 0.5)
    logit += w["delivery_speed_days"] * ((features["delivery_speed_days"] - 1.0) / 6.0 - 0.5)
    logit += w["inter_30d_x_payment"] * features["user_return_rate_30d"] * features["payment_method_risk"]
    logit += (
        w["inter_amount_x_device_risk"]
        * max(features["amount_vs_user_aov_ratio"] - 1.0, 0.0)
        * (1.0 - features["device_fingerprint_match"])
    )
    logit += w["inter_90d_x_category"] * features["user_return_rate_90d"] * features["category_return_baseline"]
    logit += HIDDEN_SCALE * (_hidden_logit(hidden) - HIDDEN_MEAN)
    logit += noise
    return 1.0 / (1.0 + math.exp(-logit))


def _seasonal_dates(num_orders: int, start: datetime, rng: random.Random) -> list[datetime]:
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
    return float(min(np_rng.exponential(12.0), DEFAULT_DAYS_SINCE_LAST_ORDER))


def get_scenario_metadata() -> dict[str, Any]:
    return {
        "stage": "premium",
        "label": "Stage 3: Premium merchant",
        "visible_features": list(FEATURES),
        "num_features": len(FEATURES),
        "hidden_scale": HIDDEN_SCALE,
        "label_noise_std": LABEL_NOISE_STD,
        "seed": SEED,
        "newly_visible_features": ["product_rating", "delivery_speed_days"],
        "target_pr_auc": "~0.94",
    }


def generate_return_risk_dataset(
    n_orders: int = 10000,
    seed: int = SEED,
    orders_per_user: int = 20,
    window_days: int = 365,
) -> pd.DataFrame:
    """Generate a flat table of scored orders with the nine model features.

    Signature and return type identical to Stages 1 and 2.
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
                    "product_rating": hidden["product_rating"],
                    "delivery_speed_days": hidden["delivery_speed_days"],
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
                        **{f"hidden_{k}": v for k, v in hidden.items()},
                    }
                )

    df = pd.DataFrame(rows).head(n_orders).reset_index(drop=True)
    df.attrs["seed"] = seed
    df.attrs["scenario"] = "premium"
    return df


def base_rate(df: pd.DataFrame) -> float:
    return float(df["returned"].mean())


if __name__ == "__main__":
    d = generate_return_risk_dataset(n_orders=1000, seed=SEED)
    print(d.head())
    print(f"\nRows: {len(d)}  Base rate: {base_rate(d):.3f}")
    print("Feature means:\n", d[FEATURES].mean().round(3).to_string())
    print("\nScenario metadata:\n", get_scenario_metadata())
