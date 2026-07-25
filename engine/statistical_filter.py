import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    action: Literal["ALLOW", "ESCALATE", "BLOCK"] = "ALLOW"
    stage: str = "velocity"
    triggered_rules: list[str] = field(default_factory=list)
    rule_details: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    population_stats: dict | None = None


@dataclass
class VelocityRule:
    name: str
    condition: Callable[..., bool]
    action: Literal["ALLOW", "ESCALATE", "BLOCK"]
    severity: int
    description: str = ""


class VelocityFilter:
    RULES: list[VelocityRule] = []

    def __init__(self, redis_client=None, config: dict | None = None):
        self.redis = redis_client
        self.config = config or {}
        self._init_rules()

    def _init_rules(self):
        self.RULES = [
            VelocityRule(
                name="V-RULE-01",
                condition=lambda v, d, **kw: v.get("txn_count_5m", 0) > 10 and (d or {}).get("baseline_txn_count_24h", 999) < 5,
                action="BLOCK",
                severity=5,
                description="Burst attack: 5min count > 10 with low baseline",
            ),
            VelocityRule(
                name="V-RULE-02",
                condition=self._zscore_rule,
                action="ESCALATE",
                severity=3,
                description="Txn count Z-score exceeds threshold",
            ),
            VelocityRule(
                name="V-RULE-03",
                condition=lambda v, d, **kw: v.get("amount_total_1h", 0) > 5 * (d or {}).get("median_amount_30d", 500) and v.get("txn_count_1h", 0) > 3,
                action="ESCALATE",
                severity=4,
                description="Amount sum > 5x median with elevated count",
            ),
            VelocityRule(
                name="V-RULE-04",
                condition=lambda v, d, **kw: v.get("device_txn_count_24h", 0) > 20 and v.get("distinct_users_last_24h", 1) > 1,
                action="BLOCK",
                severity=5,
                description="Device flood: >20 txns across multiple users",
            ),
            VelocityRule(
                name="V-RULE-05",
                condition=lambda v, d, **kw: v.get("ip_txn_count_5m", 0) > 15,
                action="ESCALATE",
                severity=3,
                description="IP burst: >15 txns from same IP in 5min",
            ),
            VelocityRule(
                name="V-RULE-06",
                condition=lambda v, d, **kw: v.get("distinct_merchants_1h", 0) > 10,
                action="ESCALATE",
                severity=4,
                description="Card testing: >10 distinct merchants in 1h",
            ),
        ]

    def _zscore_rule(self, velocity_features: dict, deviation_features: dict | None, **kw) -> bool:
        if not deviation_features:
            return False
        z = abs(deviation_features.get("amount_z_score", 0))
        return z > (self.config.get("velocity_zscore_threshold", 3.0))

    async def evaluate(self, velocity_features: dict, deviation_features: dict | None = None, whitelist: set[str] | None = None) -> FilterResult:
        start = time.perf_counter()
        triggered = []

        for rule in sorted(self.RULES, key=lambda r: -r.severity):
            try:
                if rule.condition(velocity_features, deviation_features):
                    triggered.append(rule)
            except Exception as e:
                logger.warning(f"Rule {rule.name} evaluation error: {e}")

        population_stats = await self._compute_population_baseline(velocity_features) if self.redis else None

        if not triggered:
            elapsed = (time.perf_counter() - start) * 1000
            return FilterResult(action="ALLOW", latency_ms=round(elapsed, 3), population_stats=population_stats)

        has_block = any(r.action == "BLOCK" for r in triggered)
        max_severity = max(r.severity for r in triggered)
        severity_sum = sum(r.severity for r in triggered)

        if has_block:
            action = "BLOCK"
            confidence = 1.0
        elif max_severity >= 4 or severity_sum >= 7:
            action = "ESCALATE"
            confidence = min(1.0, severity_sum / 10.0)
        else:
            action = "ALLOW"
            confidence = 0.0

        elapsed = (time.perf_counter() - start) * 1000
        return FilterResult(
            action=action,
            triggered_rules=[r.name for r in triggered],
            rule_details=[{"name": r.name, "severity": r.severity, "action": r.action} for r in triggered],
            confidence=round(confidence, 4),
            latency_ms=round(elapsed, 3),
            population_stats=population_stats,
        )

    async def _compute_population_baseline(self, features: dict) -> dict | None:
        try:
            return {
                "pop_mean_txn_count_1h": features.get("txn_count_1h", 0),
                "pop_std_txn_count_1h": features.get("txn_count_1h", 0) * 0.5 if features.get("txn_count_1h", 0) > 0 else 1.0,
                "pop_mean_amount_sum_1h": features.get("amount_total_1h", 0),
                "sampled_at": time.time(),
            }
        except Exception:
            return None


import math
from dataclasses import dataclass


@dataclass
class GeoPoint:
    lat: float
    lon: float
    timestamp: float = 0.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def geo_velocity_kmh(last_loc: GeoPoint, current_loc: GeoPoint) -> float:
    distance_km = haversine(last_loc.lat, last_loc.lon, current_loc.lat, current_loc.lon)
    hours = abs(current_loc.timestamp - last_loc.timestamp) / 3600.0
    return distance_km / hours if hours > 0 else float("inf")


class GeoSpatialFilter:
    HIGH_RISK_COUNTRIES: list[str] = []
    GEO_FENCE_ENABLED = True

    def __init__(self, redis_client=None, config: dict | None = None):
        self.redis = redis_client
        self.config = config or {}
        self.max_velocity_kmh = self.config.get("geo_velocity_max_kmh", 900.0)
        self.HIGH_RISK_COUNTRIES = self.config.get("high_risk_countries", [])

    async def evaluate(self, current_loc: GeoPoint, last_loc: GeoPoint | None, baseline: dict | None = None, account_age_days: float = 365.0, user_country: str | None = None, txn_country: str | None = None) -> FilterResult:
        start = time.perf_counter()
        triggered: list[dict] = []

        if last_loc and last_loc.timestamp > 0:
            velocity = geo_velocity_kmh(last_loc, current_loc)

            if velocity > self.max_velocity_kmh:
                triggered.append({"name": "G-RULE-01", "severity": 5, "action": "BLOCK", "detail": f"geo_velocity_{velocity:.0f}kmh"})

            if velocity > 200 and baseline:
                max_dist = baseline.get("max_location_distance_km", 100)
                dist = haversine(last_loc.lat, last_loc.lon, current_loc.lat, current_loc.lon)
                if dist > 3 * max_dist:
                    triggered.append({"name": "G-RULE-02", "severity": 4, "action": "ESCALATE", "detail": f"location_deviation_{dist:.0f}km"})

        if user_country and txn_country and user_country != txn_country:
            if account_age_days < 30 and self._is_domestic_only(user_country):
                triggered.append({"name": "G-RULE-03", "severity": 3, "action": "ESCALATE", "detail": f"new_international_{user_country}_to_{txn_country}"})

        if baseline and account_age_days < 7:
            centroid_lat = baseline.get("centroid_lat", current_loc.lat)
            centroid_lon = baseline.get("centroid_lon", current_loc.lon)
            dist_from_centroid = haversine(centroid_lat, centroid_lon, current_loc.lat, current_loc.lon)
            if dist_from_centroid > 500:
                triggered.append({"name": "G-RULE-04", "severity": 4, "action": "BLOCK", "detail": f"new_account_distant_{dist_from_centroid:.0f}km"})

        if not triggered:
            elapsed = (time.perf_counter() - start) * 1000
            return FilterResult(action="ALLOW", stage="geo", latency_ms=round(elapsed, 3))

        has_block = any(t["action"] == "BLOCK" for t in triggered)
        max_severity = max(t["severity"] for t in triggered)
        severity_sum = sum(t["severity"] for t in triggered)

        if has_block:
            action = "BLOCK"
            confidence = 1.0
        elif max_severity >= 4 or severity_sum >= 7:
            action = "ESCALATE"
            confidence = min(1.0, severity_sum / 10.0)
        else:
            action = "ALLOW"
            confidence = 0.0

        elapsed = (time.perf_counter() - start) * 1000
        return FilterResult(
            action=action,
            stage="geo",
            triggered_rules=[t["name"] for t in triggered],
            rule_details=triggered,
            confidence=round(confidence, 4),
            latency_ms=round(elapsed, 3),
        )

    def _is_domestic_only(self, user_country: str) -> bool:
        return user_country not in self.HIGH_RISK_COUNTRIES
