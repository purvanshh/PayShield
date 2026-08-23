"""Locust load test for the Track 2 risk endpoints (Phase 34).

Simulates a merchant calling the return-risk scorer at checkout (most
frequent), chargeback response generation (occasional) and the profile
lookup (rare). Mirrors the style of tests/load/locustfile.py.

Run against the live stack:

    locust -f tests/load/test_return_risk_load.py \\
        --host=http://localhost:8000 \\
        --users=100 --spawn-rate=10 --run-time=5m \\
        --html=reports/load_test_report.html

Acceptance criteria (to assert in the report, not here):
- /v1/return/score p95 < 50ms, error rate < 0.1%
- /v1/chargeback/respond p95 < 200ms
- no Redis connection errors (watch `redis_feature_store_hit_rate`)
"""

import random

from locust import HttpUser, between, task

USERS = ["U_CLEAN_001", "U_SERIAL_001", "U_HONEST_001", "U_FRAUD_001"]


class MerchantUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self):
        self.client.headers.update(
            {"X-API-Key": "payshield-dev-key-2026", "Content-Type": "application/json"}
        )

    @task(10)
    def score_return_risk(self):
        """Most common operation: scoring an order at checkout."""
        payload = {
            "order_id": f"ORD_LOAD_{random.randint(1, 100000)}",
            "user_id": random.choice(USERS),
            "merchant_id": "M_FASHION_001",
            "amount": random.choice([1500.00, 3500.00, 5500.00, 12000.00]),
            "currency": "INR",
            "category": random.choice(["fashion", "electronics", "home"]),
            "payment_method": "UPI",
            "cod_flag": random.random() < 0.4,
        }
        with self.client.post(
            "/v1/return/score", json=payload, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"status={response.status_code}")
                return
            data = response.json().get("data", {})
            score = data.get("return_risk_score", -1)
            if not 0 <= score <= 1:
                response.failure(f"invalid score: {score}")
            else:
                response.success()

    @task(3)
    def score_chargeback(self):
        """Less frequent: rebuttal generation for a filed dispute."""
        payload = {
            "dispute_id": f"CB_LOAD_{random.randint(1, 100000)}",
            "payment_id": f"pay_LOAD_{random.randint(1, 100000)}",
            "transaction_id": "TXN_CLEAN_001",
            "network": random.choice(["UPI", "VISA", "MASTERCARD"]),
            "reason_code": "10.4",
            "reason_description": "Fraud - Card Not Present",
            "response_deadline": "2026-09-20T00:00:00",
        }
        with self.client.post(
            "/v1/chargeback/respond", json=payload, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"status={response.status_code}")
                return
            confidence = response.json().get("data", {}).get("confidence_score", -1)
            if not 0 <= confidence <= 1:
                response.failure(f"invalid confidence: {confidence}")
            else:
                response.success()

    @task(1)
    def get_user_profile(self):
        """Occasional: merchant dashboard checking customer history."""
        user_id = random.choice(USERS)
        with self.client.get(
            f"/v1/return/profile/{user_id}", catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"status={response.status_code}")
