"""Locust load test for PayShield fraud scoring API."""

import random
import time
from locust import HttpUser, between, task


class FraudScoringUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.client.headers.update({"X-API-Key": "payshield-dev-key-2026"})
        self.txn_counter = 0

    def _make_txn(self):
        self.txn_counter += 1
        return {
            "txn_id": f"load_{int(time.time())}_{self.txn_counter}",
            "user_id": f"U_LOAD_{random.randint(1, 1000)}",
            "merchant_id": f"M_{random.randint(1, 100)}",
            "amount": round(random.uniform(100, 100000), 2),
            "timestamp": "2026-07-27T12:00:00",
            "device_fingerprint": f"DEV_LOAD_{random.randint(1, 500)}",
            "location": {"lat": round(random.uniform(8, 37), 4), "lon": round(random.uniform(68, 97), 4)},
            "mcc_code": random.choice(["6012", "5411", "5812", "7011", "7997"]),
            "txn_type": random.choice(["P2P", "P2M"]),
        }

    @task(70)
    def score_single(self):
        txn = self._make_txn()
        with self.client.post("/v1/score", json=txn, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(20)
    def score_batch(self):
        txns = [self._make_txn() for _ in range(10)]
        with self.client.post("/v1/batch", json={"transactions": txns}, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Batch failed: {resp.status_code}")

    @task(10)
    def get_investigation(self):
        txn_id = f"load_txn_{random.randint(1, 100)}"
        with self.client.get(f"/v1/investigation/{txn_id}", catch_response=True) as resp:
            if resp.status_code not in (200, 202, 404):
                resp.failure(f"Unexpected status: {resp.status_code}")
