import random
from datetime import timedelta

import numpy as np
import pandas as pd

from data.synthetic.entities import FraudPattern


class FraudInjector:
    def __init__(self, rng: random.Random, users: dict, merchants: dict, devices: dict):
        self.rng = rng
        self.users = users
        self.merchants = merchants
        self.devices = devices

    def inject_all(self, df: pd.DataFrame, fraud_ratio: float = 0.05) -> pd.DataFrame:
        n_fraud = max(1, int(len(df) * fraud_ratio))
        quarter = n_fraud // 4

        df = self.inject_mule_rings(df, num_rings=3, ring_size=10, count=quarter)
        df = self.inject_burst_attacks(df, num_attacks=quarter // 20, count=quarter)
        df = self.inject_merchant_collusion(df, num_shell=3, count=quarter)
        df = self.inject_account_takeover(df, num_atos=quarter // 5, count=quarter)

        remaining = n_fraud - df["is_fraud"].sum()
        if remaining > 0:
            extra = df[~df["is_fraud"]].sample(n=min(remaining, len(df[~df["is_fraud"]])), random_state=self.rng.randint(0, 9999))
            df.loc[extra.index, "is_fraud"] = True
            df.loc[extra.index, "fraud_pattern"] = self.rng.choice(list(FraudPattern)).value

        return df

    def inject_mule_rings(self, df: pd.DataFrame, num_rings: int = 3, ring_size: int = 10, count: int = 50) -> pd.DataFrame:
        all_users = list(self.users.keys())
        per_ring = max(1, count // (num_rings * ring_size))

        for ring_id in range(num_rings):
            ring_members = self.rng.sample(all_users, min(ring_size, len(all_users)))
            shell_mid = f"M_SHELL_RING_{ring_id}"
            self.merchants[shell_mid] = {
                "merchant_id": shell_mid,
                "name": f"Ring Merchant {ring_id}",
                "mcc_code": "other",
                "avg_txn_amount": 3000,
                "refund_rate": 0.01,
                "account_age_days": 45,
                "city_tier": 2,
                "is_shell": True,
                "category": "small",
                "benford_chi2": 0.0,
            }
            shared_device = f"D_RING_SHARED_{ring_id}"
            self.devices[shared_device] = {
                "device_id": shared_device,
                "os_family": "android",
                "app_version": "5.2.1",
                "is_emulator": True,
                "first_seen_timestamp": pd.Timestamp("2026-05-01"),
                "user_id": ring_members[0],
            }

            non_fraud = df[~df["is_fraud"]].index.tolist()
            for member in ring_members:
                for _ in range(per_ring):
                    if not non_fraud:
                        break
                    idx = self.rng.choice(non_fraud)
                    non_fraud.remove(idx)
                    df.at[idx, "user_id"] = member
                    df.at[idx, "device_fingerprint"] = shared_device
                    df.at[idx, "merchant_id"] = shell_mid
                    df.at[idx, "amount"] = round(self.rng.uniform(1000, 5000), 2)
                    df.at[idx, "is_fraud"] = True
                    df.at[idx, "fraud_pattern"] = FraudPattern.MULE_RING.value

        return df

    def inject_burst_attacks(self, df: pd.DataFrame, num_attacks: int = 5, count: int = 50) -> pd.DataFrame:
        transaction_indices = df[~df["is_fraud"]].index.tolist()
        per_attack = max(1, count // num_attacks)

        for attack_id in range(num_attacks):
            victim = self.rng.choice(list(self.users.keys()))
            base_idx = self.rng.choice(transaction_indices) if transaction_indices else None
            if base_idx is None:
                break
            base_ts = df.at[base_idx, "timestamp"]
            if isinstance(base_ts, str):
                base_ts = pd.Timestamp(base_ts)

            for j in range(min(per_attack, len(transaction_indices))):
                idx = self.rng.choice(transaction_indices)
                transaction_indices.remove(idx)
                df.at[idx, "user_id"] = victim
                df.at[idx, "amount"] = round(self.rng.uniform(500, 15000), 2)
                df.at[idx, "timestamp"] = base_ts + timedelta(minutes=j * 0.25)
                df.at[idx, "is_fraud"] = True
                df.at[idx, "fraud_pattern"] = FraudPattern.BURST_ATTACK.value

        return df

    def inject_merchant_collusion(self, df: pd.DataFrame, num_shell: int = 3, count: int = 50) -> pd.DataFrame:
        non_fraud = df[~df["is_fraud"]].index.tolist()
        per_merchant = max(1, count // num_shell)

        for i in range(num_shell):
            sm = f"M_SHELL_COLLUSION_{i}"
            self.merchants[sm] = {
                "merchant_id": sm,
                "name": f"Shell Merchant {i}",
                "mcc_code": self.rng.choice(["food", "travel"]),
                "avg_txn_amount": 999,
                "refund_rate": 0.01,
                "account_age_days": 45,
                "city_tier": 1,
                "is_shell": True,
                "category": "small",
                "benford_chi2": 18.0,
            }
            round_amounts = [999, 1999, 4999, 9999, 14999]
            for _ in range(min(per_merchant, len(non_fraud))):
                idx = self.rng.choice(non_fraud)
                non_fraud.remove(idx)
                df.at[idx, "merchant_id"] = sm
                df.at[idx, "amount"] = float(self.rng.choice(round_amounts))
                df.at[idx, "is_fraud"] = True
                df.at[idx, "fraud_pattern"] = FraudPattern.MERCHANT_COLLUSION.value

        return df

    def inject_account_takeover(self, df: pd.DataFrame, num_atos: int = 10, count: int = 50) -> pd.DataFrame:
        remote_cities = [
            (28.7041, 77.1025), (13.0827, 80.2707), (22.5726, 88.3639),
            (17.3850, 78.4867), (12.9716, 77.5946), (26.9124, 75.7873),
        ]
        non_fraud = df[~df["is_fraud"]].index.tolist()
        per_ato = max(1, count // num_atos)

        for _ in range(min(num_atos, len(non_fraud) // per_ato)):
            victim = self.rng.choice(list(self.users.keys()))
            target_lat, target_lon = self.rng.choice(remote_cities)

            for j in range(min(per_ato, len(non_fraud))):
                idx = self.rng.choice(non_fraud)
                non_fraud.remove(idx)
                df.at[idx, "user_id"] = victim
                df.at[idx, "lat"] = target_lat + self.rng.uniform(-0.02, 0.02)
                df.at[idx, "lon"] = target_lon + self.rng.uniform(-0.02, 0.02)
                df.at[idx, "amount"] = round(self.rng.uniform(20000, 50000), 2)
                df.at[idx, "is_fraud"] = True
                df.at[idx, "fraud_pattern"] = FraudPattern.ACCOUNT_TAKEOVER.value

        return df
