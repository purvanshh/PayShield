import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from data.synthetic.distributions import (
    MCC_CATEGORIES, HOUR_WEIGHTS, sample_age, sample_income_tier,
    sample_city_tier, sample_credit_score, sample_kyc_tier,
    sample_hour, sample_transaction_amount, sample_mcc_category,
    salary_day_multiplier,
)

INDIAN_CITIES = [
    ("Mumbai", 19.0760, 72.8777, "tier1"),
    ("Delhi", 28.7041, 77.1025, "tier1"),
    ("Bangalore", 12.9716, 77.5946, "tier1"),
    ("Hyderabad", 17.3850, 78.4867, "tier1"),
    ("Ahmedabad", 23.0225, 72.5714, "tier1"),
    ("Chennai", 13.0827, 80.2707, "tier1"),
    ("Kolkata", 22.5726, 88.3639, "tier1"),
    ("Pune", 18.5204, 73.8567, "tier2"),
    ("Jaipur", 26.9124, 75.7873, "tier2"),
    ("Lucknow", 26.8467, 80.9462, "tier2"),
    ("Nagpur", 21.1458, 79.0882, "tier2"),
    ("Indore", 22.7196, 75.8577, "tier2"),
    ("Bhopal", 23.2599, 77.4126, "tier2"),
    ("Surat", 21.1702, 72.8311, "tier2"),
    ("Patna", 25.5941, 85.1376, "tier2"),
    ("Nashik", 19.9975, 73.7898, "tier3"),
    ("Ranchi", 23.3441, 85.3096, "tier3"),
    ("Guwahati", 26.1445, 91.7362, "tier3"),
    ("Jodhpur", 26.2389, 73.0243, "tier3"),
    ("Raipur", 21.2514, 81.6296, "tier3"),
    ("Dehradun", 30.3165, 78.0322, "tier3"),
    ("Chandigarh", 30.7333, 76.7794, "tier1"),
]

TXN_TYPES = ["P2P", "P2M", "COLLECT"]


class SyntheticUPIGenerator:
    def __init__(
        self,
        n_users: int = 10_000,
        n_merchants: int = 1_000,
        n_transactions: int = 50_000,
        fraud_ratio: float = 0.05,
        seed: int = 42,
    ):
        self.n_users = n_users
        self.n_merchants = n_merchants
        self.n_transactions = n_transactions
        self.fraud_ratio = fraud_ratio
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        self.users = {}
        self.merchants = {}
        self.devices = {}
        self._city_map = {c[3]: c for c in INDIAN_CITIES}

    def _pick_city(self, tier: str) -> tuple:
        candidates = [c for c in INDIAN_CITIES if c[3] == tier]
        return self.rng.choice(candidates)

    def generate(self) -> pd.DataFrame:
        self._generate_users()
        self._generate_merchants()
        self._generate_devices()
        df = self._generate_transactions()
        return df

    def _generate_users(self):
        for i in range(self.n_users):
            uid = f"U{str(i).zfill(6)}"
            age = sample_age(self.rng)
            income_tier = sample_income_tier(self.rng)
            city_tier_label = sample_city_tier(self.rng)
            city_name, lat, lon, _ = self._pick_city(city_tier_label)
            city_tier = int(city_tier_label[-1])
            credit_score = sample_credit_score(self.rng)
            kyc = sample_kyc_tier(self.rng)
            account_age = self.rng.randint(30, 1200)
            avg_monthly = self.rng.choices([5, 15, 30, 60, 100], weights=[20, 35, 25, 15, 5])[0]
            device_count = self.rng.randint(1, 3)
            preferred_cats = self.rng.sample(MCC_CATEGORIES, k=self.rng.randint(2, 5))
            typical_hour = sample_hour(self.rng)
            median_amt = sample_transaction_amount(self.rng, city_tier_label, income_tier, 500)

            income_labels = {1: "low", 2: "low", 3: "medium", 4: "high", 5: "high"}
            self.users[uid] = {
                "user_id": uid,
                "age": age,
                "income_tier": income_tier,
                "income_tier_label": income_labels[income_tier],
                "city_tier": city_tier,
                "city_tier_label": city_tier_label,
                "credit_score": credit_score,
                "account_age_days": account_age,
                "kyc_tier": kyc,
                "preferred_mcc_categories": preferred_cats,
                "typical_txn_hour": typical_hour,
                "typical_txn_amount_median": median_amt,
                "avg_monthly_txn_count": avg_monthly,
                "device_count": device_count,
                "city": city_name,
                "lat": lat + self.rng.uniform(-0.03, 0.03),
                "lon": lon + self.rng.uniform(-0.03, 0.03),
            }

    def _generate_merchants(self):
        for i in range(self.n_merchants):
            mid = f"M{str(i).zfill(5)}"
            mcc = self.rng.choice(MCC_CATEGORIES)
            category = self.rng.choices(["small", "medium", "large"], weights=[40, 35, 25])[0]
            avg_txn = {"small": self.rng.randint(50, 500),
                       "medium": self.rng.randint(200, 2000),
                       "large": self.rng.randint(1000, 10000)}[category]
            city_tier = self.rng.randint(1, 4)
            self.merchants[mid] = {
                "merchant_id": mid,
                "name": f"Merchant_{mid}",
                "mcc_code": mcc,
                "avg_txn_amount": avg_txn,
                "refund_rate": round(self.rng.uniform(0.0, 0.08), 4),
                "account_age_days": self.rng.randint(30, 1500),
                "city_tier": city_tier,
                "is_shell": False,
                "category": category,
                "benford_chi2": 0.0,
            }

    def _generate_devices(self):
        for uid, user_data in self.users.items():
            for d in range(user_data["device_count"]):
                did = f"D{uid}_{d}"
                self.devices[did] = {
                    "device_id": did,
                    "os_family": self.rng.choice(["android", "ios"], weights=[80, 20]),
                    "app_version": f"{self.rng.randint(3, 8)}.{self.rng.randint(0, 9)}.{self.rng.randint(0, 9)}",
                    "is_emulator": self.rng.random() < 0.02,
                    "first_seen_timestamp": datetime(2026, 1, 1) + timedelta(days=self.rng.randint(0, 180)),
                    "user_id": uid,
                }

    def _generate_timestamps(self, n: int) -> list[datetime]:
        start = datetime(2026, 6, 1)
        timestamps = []
        for _ in range(n):
            day = self.rng.randint(0, 29)
            hour = self.rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
            minute = self.rng.randint(0, 59)
            second = self.rng.randint(0, 59)
            t = start + timedelta(days=day, hours=hour, minutes=minute, seconds=second)
            timestamps.append(t)
        timestamps.sort()
        return timestamps

    def _generate_transactions(self) -> pd.DataFrame:
        timestamps = self._generate_timestamps(self.n_transactions)
        device_ids = list(self.devices.keys())
        user_ids = list(self.users.keys())
        merchant_ids = list(self.merchants.keys())

        records = []
        for i in range(self.n_transactions):
            uid = self.rng.choice(user_ids)
            user = self.users[uid]
            mid = self.rng.choice(merchant_ids)
            merchant = self.merchants[mid]

            user_devices = [d for d in device_ids if d.startswith(f"D{uid[1:]}_")]
            did = self.rng.choice(user_devices) if user_devices else self.rng.choice(device_ids)

            sm = salary_day_multiplier(timestamps[i])
            amount = round(
                sample_transaction_amount(self.rng, user["city_tier_label"], user["income_tier"], merchant["avg_txn_amount"]) * sm,
                2,
            )
            amount = max(1.0, amount)

            lat_jitter = self.rng.uniform(-0.02, 0.02)
            lon_jitter = self.rng.uniform(-0.02, 0.02)

            records.append({
                "txn_id": f"TXN{str(i).zfill(8)}",
                "user_id": uid,
                "merchant_id": mid,
                "amount": amount,
                "timestamp": timestamps[i],
                "device_fingerprint": did,
                "lat": user["lat"] + lat_jitter,
                "lon": user["lon"] + lon_jitter,
                "mcc_code": merchant["mcc_code"],
                "txn_type": self.rng.choices(TXN_TYPES, weights=[30, 60, 10])[0],
                "status": "SUCCESS",
                "is_fraud": False,
                "fraud_pattern": None,
            })

        return pd.DataFrame(records)

    def save_to_parquet(self, df: pd.DataFrame, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)

    def to_dicts(self):
        return {
            "users": self.users,
            "merchants": self.merchants,
            "devices": self.devices,
        }
