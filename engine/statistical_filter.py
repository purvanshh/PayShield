import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from data.features.benford import benford_chi2
from data.features.geospatial import haversine


@dataclass
class StatisticalResult:
    decision: Literal["ALLOW", "BLOCK", "ESCALATE"] = "ALLOW"
    triggered_rules: list[str] = field(default_factory=list)
    velocity_stats: dict | None = None
    benford_chi2: float | None = None


class StatisticalFilter:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.velocity_zscore_threshold = self.config.get("velocity_zscore_threshold", 3.0)
        self.burst_5min_threshold = self.config.get("burst_5min_threshold", 10)
        self.amount_deviation_factor = self.config.get("amount_deviation_factor", 5.0)
        self.geo_velocity_max_kmh = self.config.get("geo_velocity_max_kmh", 900.0)
        self.benford_chi2_critical = self.config.get("benford_chi2_critical", 15.51)
        self.min_benford_samples = self.config.get("min_benford_samples", 20)

    def evaluate(self, txn, feature_store) -> StatisticalResult:
        if hasattr(txn, "model_dump"):
            txn_data = txn.model_dump()
        else:
            txn_data = txn
        if isinstance(txn_data.get("timestamp"), datetime):
            txn_ts = txn_data["timestamp"].timestamp()
        else:
            txn_ts = time.time()

        triggered = []
        velocity_stats = None

        velocity_stats = feature_store.get_velocity_stats(txn_data["user_id"])
        baseline = feature_store.get_user_baseline(txn_data["user_id"])

        if velocity_stats:
            z = self._compute_z_score(velocity_stats, baseline)
            if z > self.velocity_zscore_threshold:
                triggered.append(f"velocity_zscore_{z:.2f}")

            if velocity_stats["txn_count_5min"] > self.burst_5min_threshold:
                triggered.append(f"burst_5min_{velocity_stats['txn_count_5min']}")

            if baseline:
                median_amount = baseline.get("median_amount", 500)
                ratio = txn_data["amount"] / median_amount if median_amount > 0 else 1
                if ratio > self.amount_deviation_factor and velocity_stats["txn_count_24h"] > 3:
                    triggered.append(f"amount_deviation_{ratio:.1f}x")

        last_geo = feature_store.get_geospatial_cache(txn_data["user_id"])
        if last_geo and "lat" in txn_data:
            distance = haversine(
                last_geo["lat"], last_geo["lon"],
                txn_data["lat"], txn_data["lon"],
            )
            time_delta = abs(txn_ts - last_geo["timestamp"])
            hours = time_delta / 3600.0
            if hours > 0:
                geo_vel = distance / hours
                if geo_vel > self.geo_velocity_max_kmh:
                    triggered.append(f"geo_impossible_{geo_vel:.0f}kmh")

        merchant_amounts = None
        chi2_val = 0.0
        if hasattr(feature_store, "get_merchant_amounts"):
            merchant_amounts = feature_store.get_merchant_amounts(txn_data["merchant_id"])
        if merchant_amounts and len(merchant_amounts) >= self.min_benford_samples:
            chi2_val = benford_chi2(merchant_amounts)
            if chi2_val > self.benford_chi2_critical:
                triggered.append(f"benford_deviation_{chi2_val:.2f}")

        if not triggered:
            return StatisticalResult(decision="ALLOW", triggered_rules=[], velocity_stats=velocity_stats, benford_chi2=chi2_val)

        has_block = any("geo_impossible" in r for r in triggered)
        decision = "BLOCK" if has_block else "ESCALATE"

        return StatisticalResult(
            decision=decision,
            triggered_rules=triggered,
            velocity_stats=velocity_stats,
            benford_chi2=chi2_val if chi2_val > 0 else None,
        )

    def _compute_z_score(self, velocity_stats: dict, baseline: dict | None) -> float:
        recent = velocity_stats.get("txn_count_1h", 0)
        if baseline is None:
            return 0.0
        mean = baseline.get("hourly_avg_txn_count", 1.0)
        std = baseline.get("hourly_std_txn_count", 1.0)
        if std == 0:
            return 0.0
        return (recent - mean) / std
