import random

import numpy as np

CITY_TIER_WEIGHTS = {"tier1": 0.30, "tier2": 0.40, "tier3": 0.20, "tier4": 0.10}
INCOME_TIER_WEIGHTS = {1: 0.15, 2: 0.25, 3: 0.35, 4: 0.20, 5: 0.05}
KYC_TIER_WEIGHTS = {1: 0.10, 2: 0.50, 3: 0.40}
HOUR_WEIGHTS = [
    2, 1, 1, 1, 1, 2, 4, 6, 8, 10, 12, 15, 18, 15, 12, 10, 8, 10, 15, 20, 18, 12, 8, 4,
]
MCC_CATEGORIES = [
    "food", "travel", "utilities", "fashion", "groceries",
    "entertainment", "health", "education", "transport", "rent",
    "recharge", "insurance", "investment", "cashback", "other",
]


def sample_age(rng: random.Random) -> int:
    return int(max(18, min(70, rng.gauss(32, 12))))


def sample_income_tier(rng: random.Random) -> int:
    tiers, weights = zip(*INCOME_TIER_WEIGHTS.items())
    return rng.choices(tiers, weights=weights)[0]


def sample_city_tier(rng: random.Random) -> str:
    tiers, weights = zip(*CITY_TIER_WEIGHTS.items())
    return rng.choices(tiers, weights=weights)[0]


def sample_credit_score(rng: random.Random) -> int:
    return max(300, min(900, int(rng.gauss(720, 80))))


def sample_kyc_tier(rng: random.Random) -> int:
    tiers, weights = zip(*KYC_TIER_WEIGHTS.items())
    return rng.choices(tiers, weights=weights)[0]


def sample_hour(rng: random.Random) -> int:
    return rng.choices(range(24), weights=HOUR_WEIGHTS)[0]


def sample_transaction_amount(rng: random.Random, city_tier: str, income_tier: int, merchant_avg: float) -> float:
    city_mult = {"tier1": 1.5, "tier2": 1.0, "tier3": 0.7, "tier4": 0.5}[city_tier]
    income_mult = {1: 0.5, 2: 0.8, 3: 1.0, 4: 1.5, 5: 2.5}[income_tier]
    base = merchant_avg * city_mult * income_mult
    noise = rng.gauss(0, base * 0.3)
    return max(1.0, round(base + noise, 2))


def sample_mcc_category(rng: random.Random) -> str:
    return rng.choice(MCC_CATEGORIES)


def is_salary_day(timestamp) -> bool:
    return timestamp.day <= 5


def salary_day_multiplier(timestamp) -> float:
    return 1.4 if is_salary_day(timestamp) else 1.0
