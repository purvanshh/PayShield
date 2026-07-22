import math
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

INDIAN_CITIES = [
    ("Mumbai", 19.0760, 72.8777, "T1"),
    ("Delhi", 28.7041, 77.1025, "T1"),
    ("Bangalore", 12.9716, 77.5946, "T1"),
    ("Hyderabad", 17.3850, 78.4867, "T1"),
    ("Ahmedabad", 23.0225, 72.5714, "T1"),
    ("Chennai", 13.0827, 80.2707, "T1"),
    ("Kolkata", 22.5726, 88.3639, "T1"),
    ("Pune", 18.5204, 73.8567, "T2"),
    ("Jaipur", 26.9124, 75.7873, "T2"),
    ("Lucknow", 26.8467, 80.9462, "T2"),
    ("Nagpur", 21.1458, 79.0882, "T2"),
    ("Indore", 22.7196, 75.8577, "T2"),
    ("Bhopal", 23.2599, 77.4126, "T2"),
    ("Visakhapatnam", 17.6868, 83.2185, "T2"),
    ("Vadodara", 22.3072, 73.1812, "T2"),
    ("Surat", 21.1702, 72.8311, "T2"),
    ("Coimbatore", 11.0168, 76.9558, "T2"),
    ("Patna", 25.5941, 85.1376, "T2"),
    ("Ludhiana", 30.9010, 75.8573, "T2"),
    ("Agra", 27.1767, 78.0081, "T2"),
    ("Nashik", 19.9975, 73.7898, "T3"),
    ("Ranchi", 23.3441, 85.3096, "T3"),
    ("Guwahati", 26.1445, 91.7362, "T3"),
    ("Jodhpur", 26.2389, 73.0243, "T3"),
    ("Raipur", 21.2514, 81.6296, "T3"),
    ("Dehradun", 30.3165, 78.0322, "T3"),
    ("Chandigarh", 30.7333, 76.7794, "T1"),
]

MCC_CATEGORIES = [
    "food", "travel", "utilities", "fashion", "groceries",
    "entertainment", "health", "education", "transport", "rent",
    "recharge", "insurance", "investment", "cashback", "other",
]

TXN_TYPES = ["P2P", "P2M", "COLLECT"]


def _random_demographics(rng: random.Random) -> dict:
    city_name, lat, lon, tier = rng.choice(INDIAN_CITIES)
    age = rng.choices(
        [22, 27, 32, 37, 42, 47, 52, 57],
        weights=[15, 20, 20, 15, 12, 8, 5, 5],
    )[0] + rng.randint(-2, 2)
    income_tier = rng.choices(
        ["low", "medium", "high"],
        weights=[30, 50, 20],
    )[0]
    credit_score = rng.choices(
        [650, 700, 750, 800],
        weights=[10, 30, 40, 20],
    )[0] + rng.randint(-30, 30)
    return {
        "city": city_name,
        "lat": lat + rng.uniform(-0.05, 0.05),
        "lon": lon + rng.uniform(-0.05, 0.05),
        "city_tier": tier,
        "age": age,
        "income_tier": income_tier,
        "credit_score": max(300, min(900, credit_score)),
    }


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

    def _generate_users(self):
        for i in range(self.n_users):
            uid = f"U{str(i).zfill(6)}"
            demo = _random_demographics(self.rng)
            kyc_tier = self.rng.choices(["KYC1", "KYC2", "KYC3"], weights=[10, 50, 40])[0]
            account_age = self.rng.randint(30, 1200)
            avg_monthly_txn = self.rng.choices(
                [5, 15, 30, 60, 100], weights=[20, 35, 25, 15, 5],
            )[0]
            device_count = self.rng.randint(1, 3)
            self.users[uid] = {
                "user_id": uid,
                "credit_score": demo["credit_score"],
                "account_age_days": account_age,
                "kyc_tier": kyc_tier,
                "avg_monthly_txn_count": avg_monthly_txn,
                "device_count": device_count,
                "city": demo["city"],
                "city_tier": demo["city_tier"],
                "lat": demo["lat"],
                "lon": demo["lon"],
                "income_tier": demo["income_tier"],
            }

    def _generate_merchants(self):
        for i in range(self.n_merchants):
            mid = f"M{str(i).zfill(5)}"
            mcc = self.rng.choice(MCC_CATEGORIES)
            category = ["small", "medium", "large"][
                self.rng.choices([0, 1, 2], weights=[40, 35, 25])[0]
            ]
            avg_txn = {
                "small": self.rng.randint(50, 500),
                "medium": self.rng.randint(200, 2000),
                "large": self.rng.randint(1000, 10000),
            }[category]
            self.merchants[mid] = {
                "merchant_id": mid,
                "category_code": mcc,
                "avg_txn_amount": avg_txn,
                "refund_rate": round(self.rng.uniform(0.0, 0.08), 4),
                "account_age_days": self.rng.randint(30, 1500),
                "benford_chi2": 0.0,
                "category": category,
            }

    def _generate_devices(self, user_ids: list[str]):
        for uid in user_ids:
            device_count = self.users[uid]["device_count"]
            for d in range(device_count):
                did = f"D{uid}_{d}"
                is_emulator = self.rng.random() < 0.02
                self.devices[did] = {
                    "device_id": did,
                    "os_family": self.rng.choice(["android", "ios"], weights=[80, 20]),
                    "app_version": f"{self.rng.randint(3, 8)}.{self.rng.randint(0, 9)}.{self.rng.randint(0, 9)}",
                    "is_emulator": is_emulator,
                    "first_seen_timestamp": datetime(2026, 1, 1) + timedelta(days=self.rng.randint(0, 180)),
                    "user_id": uid,
                }

    def _generate_timestamps(self) -> list[datetime]:
        start = datetime(2026, 6, 1)
        timestamps = []
        for _ in range(self.n_transactions):
            day = self.rng.randint(0, 29)
            hour = self.rng.choices(
                list(range(24)),
                weights=[2, 1, 1, 1, 1, 2, 4, 6, 8, 10, 12, 15, 18, 15, 12, 10, 8, 10, 15, 20, 18, 12, 8, 4],
            )[0]
            minute = self.rng.randint(0, 59)
            second = self.rng.randint(0, 59)
            t = start + timedelta(days=day, hours=hour, minutes=minute, seconds=second)
            timestamps.append(t)
        timestamps.sort()
        return timestamps

    def generate(self) -> pd.DataFrame:
        self._generate_users()
        self._generate_merchants()

        user_ids = list(self.users.keys())
        merchant_ids = list(self.merchants.keys())
        self._generate_devices(user_ids)

        timestamps = self._generate_timestamps()
        device_ids = list(self.devices.keys())

        records = []
        for i in range(self.n_transactions):
            uid = self.rng.choice(user_ids)
            user = self.users[uid]
            mid = self.rng.choice(merchant_ids)
            merchant = self.merchants[mid]
            user_devices = [d for d in device_ids if d.startswith(f"D{uid[1:]}_")]
            did = self.rng.choice(user_devices) if user_devices else device_ids[0]

            amount = round(
                self.rng.gauss(merchant["avg_txn_amount"], merchant["avg_txn_amount"] * 0.3)
                if self.rng.random() > 0.3
                else self.rng.uniform(10, 50000),
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
                "mcc_code": merchant["category_code"],
                "txn_type": self.rng.choices(TXN_TYPES, weights=[30, 60, 10])[0],
                "is_fraud": False,
                "fraud_type": None,
            })

        df = pd.DataFrame(records)
        df = self.inject_fraud(df)
        return df

    def inject_fraud(self, df: pd.DataFrame) -> pd.DataFrame:
        n_fraud = int(len(df) * self.fraud_ratio)
        fraud_indices = self.rng.sample(range(len(df)), n_fraud)
        quarter = n_fraud // 4

        mule_indices = fraud_indices[:quarter]
        burst_indices = fraud_indices[quarter:2*quarter]
        collusion_indices = fraud_indices[2*quarter:3*quarter]
        ato_indices = fraud_indices[3*quarter:]

        mule_ring_users = self.rng.sample(list(self.users.keys()), 5)
        for _ in range(10):
            extra = f"U_mule_{len(self.users) + _}"
            self.users[extra] = self.users[mule_ring_users[0]].copy()
            self.users[extra]["user_id"] = extra

        shared_device = "D_mule_shared"
        self.devices[shared_device] = {
            "device_id": shared_device,
            "os_family": "android",
            "app_version": "5.2.1",
            "is_emulator": True,
            "first_seen_timestamp": datetime(2026, 5, 1),
        }

        for idx in mule_indices:
            row = df.iloc[idx]
            ring_user = self.rng.choice(list(self.users.keys())[-15:])
            df.at[idx, "user_id"] = ring_user
            df.at[idx, "device_fingerprint"] = shared_device
            df.at[idx, "amount"] = round(self.rng.uniform(1000, 5000), 2)
            df.at[idx, "merchant_id"] = self.rng.choice(list(self.merchants.keys()))
            df.at[idx, "is_fraud"] = True
            df.at[idx, "fraud_type"] = "MULE_RING"

        for idx in burst_indices:
            base_idx = idx // 20 * 20
            burst_user = self.rng.choice(list(self.users.keys()))
            base_t = df.iloc[base_idx]["timestamp"]
            for offset in range(min(20, len(burst_indices) - burst_indices.tolist().index(idx))):
                if base_idx + offset >= len(df):
                    break
                df.at[base_idx + offset, "user_id"] = burst_user
                df.at[base_idx + offset, "amount"] = round(self.rng.uniform(500, 15000), 2)
                df.at[base_idx + offset, "timestamp"] = base_t + timedelta(minutes=offset * 0.25)
                df.at[base_idx + offset, "is_fraud"] = True
                df.at[base_idx + offset, "fraud_type"] = "BURST_ATTACK"

        shell_merchants = [f"M_shell_{i}" for i in range(3)]
        for i, sm in enumerate(shell_merchants):
            self.merchants[sm] = {
                "merchant_id": sm,
                "category_code": "other",
                "avg_txn_amount": 999,
                "refund_rate": 0.01,
                "account_age_days": 45,
                "benford_chi2": 18.0,
                "category": "small",
            }

        for idx in collusion_indices:
            sm = self.rng.choice(shell_merchants)
            df.at[idx, "merchant_id"] = sm
            df.at[idx, "amount"] = round(self.rng.choice([999, 1999, 4999, 9999]), 2)
            df.at[idx, "is_fraud"] = True
            df.at[idx, "fraud_type"] = "MERCHANT_COLLUSION"

        for idx in ato_indices:
            victim = self.rng.choice(list(self.users.keys()))
            target_city = self.rng.choice(INDIAN_CITIES)
            df.at[idx, "user_id"] = victim
            df.at[idx, "lat"] = target_city[1] + self.rng.uniform(-0.01, 0.01)
            df.at[idx, "lon"] = target_city[2] + self.rng.uniform(-0.01, 0.01)
            df.at[idx, "amount"] = round(self.rng.uniform(20000, 50000), 2)
            df.at[idx, "is_fraud"] = True
            df.at[idx, "fraud_type"] = "ATO"

        return df
