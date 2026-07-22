import time

import numpy as np


class VelocityComputer:
    def __init__(self, feature_store):
        self.feature_store = feature_store

    def count_last_hour(self, user_id: str) -> int:
        cutoff = time.time() - 3600
        return self.feature_store.zcount(f"velocity:{user_id}", cutoff, time.time())

    def count_last_5min(self, user_id: str) -> int:
        cutoff = time.time() - 300
        return self.feature_store.zcount(f"velocity:{user_id}", cutoff, time.time())

    def count_last_24h(self, user_id: str) -> int:
        cutoff = time.time() - 86400
        return self.feature_store.zcount(f"velocity:{user_id}", cutoff, time.time())

    def z_score(self, user_id: str) -> float:
        recent = self.count_last_24h(user_id)
        baseline = self.feature_store.get_user_baseline(user_id)
        if baseline is None:
            return 0.0
        mean = baseline.get("daily_avg_txn_count", 10)
        std = baseline.get("daily_std_txn_count", 5)
        if std == 0:
            return 0.0
        return (recent - mean) / std
