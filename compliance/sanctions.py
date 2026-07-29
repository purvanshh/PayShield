import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SANCTIONS_LIST = ["OFAC_SDN", "UN_SC", "EU_FINANCIAL_SANCTIONS", "UK_HMT", "INDIA_AML"]


class SanctionsChecker:
    def __init__(self, cache_dir: str = "data/sanctions"):
        self.cache_dir = Path(cache_dir)
        self._entities: dict[str, dict] = {}
        self._loaded = False

    def load_sanctions_list(self) -> bool:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._entities = {}

            default_file = self.cache_dir / "default_sanctions.csv"
            if not default_file.exists():
                self._write_default_sanctions(default_file)

            with open(default_file, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    entity_id = row.get("entity_id", "").strip()
                    if entity_id:
                        self._entities[entity_id] = {
                            "entity_id": entity_id,
                            "name": row.get("name", ""),
                            "list": row.get("list", "OFAC_SDN"),
                            "risk_level": row.get("risk_level", "high"),
                            "country": row.get("country", ""),
                            "added_at": row.get("added_at", ""),
                        }
            self._loaded = True
            logger.info(f"Sanctions list loaded: {len(self._entities)} entities")
            return True
        except Exception as e:
            logger.warning(f"Failed to load sanctions list: {e}")
            return False

    def check_entity(self, entity_id: str) -> dict[str, Any]:
        if not self._loaded:
            self.load_sanctions_list()

        if entity_id in self._entities:
            entry = self._entities[entity_id]
            return {
                "status": "BLOCKED",
                "matched": True,
                "sanctions_list": entry["list"],
                "risk_level": entry.get("risk_level", "high"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "details": {
                    "name": entry.get("name", ""),
                    "country": entry.get("country", ""),
                },
            }

        return {
            "status": "CLEAR",
            "matched": False,
            "sanctions_list": "NONE",
            "risk_level": "none",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": {},
        }

    def check_entity_name(self, name: str) -> dict[str, Any]:
        if not self._loaded:
            self.load_sanctions_list()

        name_lower = name.lower().strip()
        for entity_id, entry in self._entities.items():
            if name_lower in entry.get("name", "").lower():
                return {
                    "status": "BLOCKED",
                    "matched": True,
                    "sanctions_list": entry["list"],
                    "risk_level": entry.get("risk_level", "high"),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "details": {
                        "entity_id": entity_id,
                        "name": entry.get("name", ""),
                        "country": entry.get("country", ""),
                    },
                }

        return {
            "status": "CLEAR",
            "matched": False,
            "sanctions_list": "NONE",
            "risk_level": "none",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": {},
        }

    def _write_default_sanctions(self, filepath: Path):
        default_entries = [
            {"entity_id": "SANCTION_001", "name": "KHALID BIN AL-WALEED", "list": "OFAC_SDN", "risk_level": "high", "country": "XX"},
            {"entity_id": "SANCTION_002", "name": "NORTH KOREAN TRADING CORP", "list": "UN_SC", "risk_level": "high", "country": "KP"},
            {"entity_id": "SANCTION_003", "name": "IRANIAN REVOLUTIONARY GUARD", "list": "OFAC_SDN", "risk_level": "high", "country": "IR"},
        ]
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["entity_id", "name", "list", "risk_level", "country", "added_at"])
            writer.writeheader()
            for entry in default_entries:
                entry["added_at"] = datetime.now(timezone.utc).isoformat()
                writer.writerow(entry)
        logger.info(f"Default sanctions list written: {filepath}")


class AMLComplianceEngine:
    def __init__(self):
        self.velocity_thresholds = {
            "txn_count_24h": 100,
            "amount_sum_24h": 500000,
            "txn_count_1h": 20,
            "structuring_count_30d": 10,
            "structuring_threshold": 9500,
        }

    def check_velocity(self, velocity_stats: dict[str, Any]) -> dict[str, Any]:
        flags = []
        risk_score = 0

        if velocity_stats.get("txn_count_24h", 0) > self.velocity_thresholds["txn_count_24h"]:
            flags.append({"rule": "AML_VELOCITY_01", "reason": f"24h txn count > {self.velocity_thresholds['txn_count_24h']}", "severity": "medium"})
            risk_score += 0.3

        if velocity_stats.get("amount_sum_24h", 0) > self.velocity_thresholds["amount_sum_24h"]:
            flags.append({"rule": "AML_VELOCITY_02", "reason": f"24h amount sum > {self.velocity_thresholds['amount_sum_24h']}", "severity": "high"})
            risk_score += 0.4

        if velocity_stats.get("txn_count_1h", 0) > self.velocity_thresholds["txn_count_1h"]:
            flags.append({"rule": "AML_VELOCITY_03", "reason": f"1h txn count > {self.velocity_thresholds['txn_count_1h']}", "severity": "medium"})
            risk_score += 0.2

        return {
            "status": "FLAGGED" if flags else "CLEAR",
            "flags": flags,
            "risk_score": min(1.0, risk_score),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_structuring(self, transaction_history: list[dict]) -> dict[str, Any]:
        structuring_txns = []
        threshold = self.velocity_thresholds["structuring_threshold"]
        max_count = self.velocity_thresholds["structuring_count_30d"]

        for txn in transaction_history:
            amount = txn.get("amount", 0)
            if threshold * 0.8 < amount < threshold:
                structuring_txns.append(txn)

        is_structuring = len(structuring_txns) > max_count

        return {
            "status": "SUSPICIOUS" if is_structuring else "CLEAR",
            "detected": is_structuring,
            "suspicious_count": len(structuring_txns),
            "threshold": threshold,
            "rule": "AML_STRUCTURING_01",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_cross_border(self, user_country: str, txn_country: str, amount: float) -> dict[str, Any]:
        high_risk_countries = {"KP", "IR", "SY", "CU", "VE"}
        is_cross_border = user_country != txn_country
        is_high_risk = txn_country in high_risk_countries

        flags = []
        risk_score = 0.0

        if is_high_risk:
            flags.append({"rule": "AML_CROSS_BORDER_01", "reason": f"Transaction to/from high-risk country: {txn_country}", "severity": "high"})
            risk_score += 0.8
        elif is_cross_border and amount > 50000:
            flags.append({"rule": "AML_CROSS_BORDER_02", "reason": f"Large cross-border transfer: {amount}", "severity": "medium"})
            risk_score += 0.3

        return {
            "status": "FLAGGED" if flags else "CLEAR",
            "cross_border": is_cross_border,
            "high_risk_country": is_high_risk,
            "flags": flags,
            "risk_score": min(1.0, risk_score),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


class KYCVerifier:
    KYC_TIERS = {
        "KYC0": {"min": 0, "description": "No KYC - basic account"},
        "KYC1": {"min": 1, "description": "Basic KYC - name, phone verified"},
        "KYC2": {"min": 2, "description": "Standard KYC - ID document verified"},
        "KYC3": {"min": 3, "description": "Full KYC - address, biometric verified"},
    }

    def __init__(self):
        self._kyc_db: dict[str, dict] = {}

    def verify_user(self, user_id: str) -> dict[str, Any]:
        user_kyc = self._kyc_db.get(user_id, {"tier": "KYC2", "verified_at": "", "documents": []})

        tier = user_kyc.get("tier", "KYC2")
        is_verified = tier not in ("KYC0", "KYC1")

        return {
            "status": "VERIFIED" if is_verified else "PENDING",
            "kyc_tier": tier,
            "tier_description": self.KYC_TIERS.get(tier, {}).get("description", "Unknown"),
            "documents_verified": user_kyc.get("documents", []),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def set_user_kyc(self, user_id: str, tier: str, documents: list[str] | None = None):
        self._kyc_db[user_id] = {
            "tier": tier,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "documents": documents or [],
        }

    def get_kyc_tier_for_limit(self, tier: str) -> dict[str, Any]:
        limits = {
            "KYC0": {"daily_limit": 1000, "monthly_limit": 5000},
            "KYC1": {"daily_limit": 10000, "monthly_limit": 50000},
            "KYC2": {"daily_limit": 100000, "monthly_limit": 500000},
            "KYC3": {"daily_limit": 1000000, "monthly_limit": 5000000},
        }
        return limits.get(tier, limits["KYC0"])
