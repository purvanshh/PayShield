import random
from datetime import datetime

from locust import HttpUser, task, between


class PayShieldLoadTest(HttpUser):
    wait_time = between(0.01, 0.05)
    host = "http://localhost:8000"

    def on_start(self):
        self.headers = {"X-API-Key": "payshield-dev-key-2026", "Content-Type": "application/json"}

    @task(10)
    def score_transaction(self):
        payload = {
            "txn_id": f"TXN{random.randint(0, 99999999):08d}",
            "user_id": f"U{random.randint(0, 9999):06d}",
            "merchant_id": f"M{random.randint(0, 999):05d}",
            "amount": round(random.uniform(10, 50000), 2),
            "timestamp": datetime.utcnow().isoformat(),
            "device_fingerprint": f"D_U{random.randint(0, 999):06d}_{random.randint(0, 2)}",
            "location": {"lat": random.uniform(8.0, 37.0), "lon": random.uniform(68.0, 97.0)},
            "mcc_code": random.choice(["food", "travel", "utilities", "fashion", "groceries"]),
            "txn_type": random.choice(["P2P", "P2M", "COLLECT"]),
        }
        self.client.post("/v1/score", json=payload, headers=self.headers)

    @task(1)
    def health_check(self):
        self.client.get("/health")

    @task(2)
    def batch_score(self):
        txns = []
        for i in range(10):
            txns.append({
                "txn_id": f"TXN{random.randint(0, 99999999):08d}",
                "user_id": f"U{random.randint(0, 9999):06d}",
                "merchant_id": f"M{random.randint(0, 999):05d}",
                "amount": round(random.uniform(10, 50000), 2),
                "timestamp": datetime.utcnow().isoformat(),
                "device_fingerprint": "D_load_test",
                "location": {"lat": random.uniform(8.0, 37.0), "lon": random.uniform(68.0, 97.0)},
                "mcc_code": "food",
                "txn_type": "P2M",
            })
        self.client.post("/v1/batch", json={"transactions": txns}, headers=self.headers)
