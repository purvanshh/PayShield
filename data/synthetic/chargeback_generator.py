"""Synthetic chargeback dataset generator (Track 02 - Phase 18).

Generates realistic chargeback scenarios for testing the evidence
responder: transactions carrying L1/L2/L3 evidence from "transaction time"
(scored by PayShield), later disputed via standard Visa/Mastercard reason
codes, with merchant-expected outcomes.

Chargebacks differ from returns: they only occur against transactions the
pipeline ALLOWED (blocked txns never clear settlement), the reason code
class (fraud/service/processing) drives the evidence requirements, and the
response window follows per-network deadlines (UPI 7d, Visa/MC 30d).
"""

import random
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

fake = Faker("en_IN")

REASON_CODES = {
    "fraud": [
        {"code": "10.4", "desc": "Fraud - Card Not Present", "rate": 0.60},
        {"code": "10.5", "desc": "Fraud - Visa Fraud Monitoring Program", "rate": 0.15},
        {"code": "FRAUD", "desc": "Fraudulent Transaction", "rate": 0.25},
    ],
    "service": [
        {"code": "13.1", "desc": "Services Not Provided", "rate": 0.40},
        {"code": "13.2", "desc": "Merchandise Not Received", "rate": 0.30},
        {"code": "13.3", "desc": "Not as Described", "rate": 0.20},
        {"code": "13.6", "desc": "Duplicate Processing", "rate": 0.10},
    ],
    "processing": [
        {"code": "12.1", "desc": "Late Presentment", "rate": 0.30},
        {"code": "12.2", "desc": "Incorrect Transaction Code", "rate": 0.20},
        {"code": "12.4", "desc": "Incorrect Account Number", "rate": 0.50},
    ],
}

RESPONSE_WINDOWS = {"UPI": 7, "VISA": 30, "MASTERCARD": 30, "RUPAY": 15}


class ChargebackSyntheticGenerator:
    """Generates synthetic chargeback scenarios."""

    def __init__(self, seed: int = 42):
        random.seed(seed)
        fake.seed_instance(seed)
        self.seed = seed

    # ------------------------------------------------------------------ #
    # transactions                                                       #
    # ------------------------------------------------------------------ #

    def generate_transaction(
        self,
        user_id: str,
        merchant_id: str,
        txn_id: str | None = None,
        network: str | None = None,
    ) -> dict[str, Any]:
        """A transaction as the pipeline saw it (with L1/L2/L3 evidence)."""
        network = network or random.choice(["UPI", "VISA", "MASTERCARD", "RUPAY"])
        txn = {
            "txn_id": txn_id or f"TXN_{fake.uuid4()[:12]}",
            "user_id": user_id,
            "merchant_id": merchant_id,
            "amount": round(random.gauss(3500, 1500), 2),
            "timestamp": (datetime.utcnow() - timedelta(days=random.randint(30, 90))).isoformat(),
            "payment_method": network,
            "device_fingerprint": f"DEV_{fake.uuid4()[:8]}",
            "location": {"lat": float(fake.latitude()), "lon": float(fake.longitude())},
            "mcc_code": random.choice(["food", "fashion", "electronics", "travel", "grocery"]),
            "txn_type": random.choice(["P2M", "P2P"]),
        }
        txn["decision"] = "ALLOW"  # blocked txns never clear - no chargeback
        txn["l1_result"] = self._generate_l1_evidence(txn)
        if random.random() < 0.5:
            txn["l2_result"] = self._generate_l2_evidence(txn)
        if random.random() < 0.3:
            txn["l3_result"] = self._generate_l3_evidence(txn)
        return txn

    def _generate_l1_evidence(self, txn: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002 - interface symmetry
        return {
            "velocity_rules": random.sample(
                ["V-RULE-01", "V-RULE-02", "V-RULE-03", "V-RULE-04"],
                k=random.randint(0, 2),
            ),
            "geo_rules": random.sample(["G-RULE-01", "G-RULE-02", "G-RULE-03"], k=random.randint(0, 1)),
            "txn_count_5m": random.randint(1, 5),
            "txn_count_1h": random.randint(1, 10),
            "amount_total_1h": round(random.gauss(15000, 5000), 2),
            "geo_velocity_kmh": round(random.gauss(40, 20), 2) if random.random() < 0.3 else 0,
        }

    def _generate_l2_evidence(self, txn: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002 - interface symmetry
        return {
            "gnn_score": round(random.gauss(0.3, 0.2), 4),
            "anomaly_type": random.choice([None, "MERCHANT_COLLUSION", "MULE_RING", "VELOCITY_ANOMALY"]),
            "risk_paths_found": random.randint(0, 3),
            "connected_entities": random.randint(2, 8),
        }

    def _generate_l3_evidence(self, txn: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary": f"Transaction {txn['txn_id']} analyzed. Risk level: "
            f"{random.choice(['LOW', 'MEDIUM', 'HIGH'])}.",
            "quality_score": round(max(0.1, min(1.0, random.gauss(0.7, 0.15))), 2),
            "anomaly_flags": random.sample(
                ["velocity_spike", "geo_anomaly", "device_mismatch"], k=random.randint(0, 2)
            ),
        }

    # ------------------------------------------------------------------ #
    # chargebacks                                                        #
    # ------------------------------------------------------------------ #

    def generate_chargeback(
        self, transaction: dict[str, Any], dispute_type: str = "fraud"
    ) -> dict[str, Any]:
        """Dispute against an allowed transaction, inheriting its evidence."""
        reasons = REASON_CODES[dispute_type]
        weights = [r["rate"] for r in reasons]
        reason = random.choices(reasons, weights=weights)[0]
        network = transaction["payment_method"]

        chargeback = {
            "dispute_id": f"CB_{fake.uuid4()[:12]}",
            "payment_id": f"pay_{transaction['txn_id'][4:]}",
            "transaction_id": transaction["txn_id"],
            "network": network,
            "reason_code": reason["code"],
            "reason_description": reason["desc"],
            "dispute_type": dispute_type,
            "amount": transaction["amount"],
            "currency": "INR",
            "status": "open",
            "created_at": (datetime.utcnow() - timedelta(days=random.randint(1, 14))).isoformat(),
            "respond_by": (
                datetime.utcnow() + timedelta(days=random.randint(7, RESPONSE_WINDOWS.get(network, 25)))
            ).isoformat(),
            "transaction": transaction,
            "expected_outcome": random.choice(["won", "lost", "under_review"]),
        }
        return chargeback

    def generate_dataset(
        self,
        num_transactions: int = 200,
        chargeback_rate: float = 0.15,
    ) -> dict[str, Any]:
        """Full dataset: allowed transactions plus their chargeback subset."""
        transactions = []
        chargebacks = []
        for _ in range(num_transactions):
            user_id = f"U_{fake.uuid4()[:8]}"
            merchant_id = f"M_{fake.uuid4()[:8]}"
            txn = self.generate_transaction(user_id, merchant_id)
            transactions.append(txn)
            if random.random() < chargeback_rate:
                dispute_type = random.choice(["fraud", "service", "processing"])
                chargebacks.append(self.generate_chargeback(txn, dispute_type))

        return {
            "transactions": transactions,
            "chargebacks": chargebacks,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "num_transactions": len(transactions),
                "num_chargebacks": len(chargebacks),
                "chargeback_rate": len(chargebacks) / max(1, len(transactions)),
                "seed": self.seed,
            },
        }
