import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal

from configs.config_loader import settings
from engine.constants import Decision, RuleType

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    action: Decision = Decision.ALLOW
    stage: RuleType = RuleType.VELOCITY
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
    action: Decision
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
                action=Decision.BLOCK,
                severity=5,
                description="Burst attack: 5min count > 10 with low baseline",
            ),
            VelocityRule(
                name="V-RULE-02",
                condition=self._zscore_rule,
                action=Decision.ESCALATE,
                severity=3,
                description="Txn count Z-score exceeds threshold",
            ),
            VelocityRule(
                name="V-RULE-03",
                condition=lambda v, d, **kw: v.get("amount_total_1h", 0) > 5 * (d or {}).get("median_amount_30d", 500) and v.get("txn_count_1h", 0) > 3,
                action=Decision.ESCALATE,
                severity=4,
                description="Amount sum > 5x median with elevated count",
            ),
            VelocityRule(
                name="V-RULE-04",
                condition=lambda v, d, **kw: v.get("device_txn_count_24h", 0) > 20 and v.get("distinct_users_last_24h", 1) > 1,
                action=Decision.BLOCK,
                severity=5,
                description="Device flood: >20 txns across multiple users",
            ),
            VelocityRule(
                name="V-RULE-05",
                condition=lambda v, d, **kw: v.get("ip_txn_count_5m", 0) > 15,
                action=Decision.ESCALATE,
                severity=3,
                description="IP burst: >15 txns from same IP in 5min",
            ),
            VelocityRule(
                name="V-RULE-06",
                condition=lambda v, d, **kw: v.get("distinct_merchants_1h", 0) > 10,
                action=Decision.ESCALATE,
                severity=4,
                description="Card testing: >10 distinct merchants in 1h",
            ),
        ]

    def _zscore_rule(self, velocity_features: dict, deviation_features: dict | None, **kw) -> bool:
        if not deviation_features:
            return False
        z = abs(deviation_features.get("amount_z_score", 0))
        return z > self.config.get("velocity_zscore_threshold", settings.thresholds.velocity_zscore)

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
            return FilterResult(action=Decision.ALLOW, latency_ms=round(elapsed, 3), population_stats=population_stats)

        has_block = any(r.action == Decision.BLOCK for r in triggered)
        max_severity = max(r.severity for r in triggered)
        severity_sum = sum(r.severity for r in triggered)

        if has_block:
            action = Decision.BLOCK
            confidence = 1.0
        elif max_severity >= 4 or severity_sum >= 7:
            action = Decision.ESCALATE
            confidence = min(1.0, severity_sum / 10.0)
        else:
            action = Decision.ALLOW
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
        self.max_velocity_kmh = self.config.get("geo_velocity_max_kmh", settings.thresholds.geo_velocity_max_kmh)
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
            return FilterResult(action=Decision.ALLOW, stage=RuleType.GEO, latency_ms=round(elapsed, 3))

        has_block = any(t["action"] == "BLOCK" for t in triggered)
        max_severity = max(t["severity"] for t in triggered)
        severity_sum = sum(t["severity"] for t in triggered)

        if has_block:
            action = Decision.BLOCK
            confidence = 1.0
        elif max_severity >= 4 or severity_sum >= 7:
            action = Decision.ESCALATE
            confidence = min(1.0, severity_sum / 10.0)
        else:
            action = Decision.ALLOW
            confidence = 0.0

        elapsed = (time.perf_counter() - start) * 1000
        return FilterResult(
            action=action,
            stage=RuleType.GEO,
            triggered_rules=[t["name"] for t in triggered],
            rule_details=triggered,
            confidence=round(confidence, 4),
            latency_ms=round(elapsed, 3),
        )

    def _is_domestic_only(self, user_country: str) -> bool:
        return user_country not in self.HIGH_RISK_COUNTRIES


BENFORD_EXPECTED = [math.log10(1 + 1.0 / d) for d in range(1, 10)]


def first_digit(amount: float) -> int:
    s = str(abs(amount)).lstrip("0").replace(".", "")
    return int(s[0]) if s else 1


def benford_chi2(observed_counts: list[int]) -> float:
    n = sum(observed_counts)
    if n == 0:
        return 0.0
    expected = [n * p for p in BENFORD_EXPECTED]
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed_counts, expected) if e > 0)
    return round(chi2, 4)


@dataclass
class BenfordStats:
    merchant_id: str
    observed_counts: list[int] = field(default_factory=lambda: [0] * 9)
    total_transactions: int = 0
    chi2_statistic: float = 0.0
    is_anomalous: bool = False


class BenfordFilter:
    CHI2_CRITICAL_005 = 15.51
    CHI2_CRITICAL_001 = 20.09
    MIN_SAMPLES = 20
    BENFORD_PREFIX = "benford"

    def __init__(self, redis_client=None, config: dict | None = None):
        self.redis = redis_client
        self.config = config or {}
        self.critical_005 = self.config.get("benford_chi2_critical", settings.thresholds.benford_chi2_critical)
        self.critical_001 = self.config.get("benford_chi2_critical_001", self.CHI2_CRITICAL_001)
        self.min_samples = self.config.get("min_benford_samples", settings.thresholds.min_benford_samples)
        self.whitelisted_merchants: set[str] = set(self.config.get("benford_whitelist", []))

    def _merchant_key(self, merchant_id: str) -> str:
        return f"{self.BENFORD_PREFIX}:{merchant_id}"

    async def update_merchant_distribution(self, merchant_id: str, amount: float):
        if merchant_id in self.whitelisted_merchants:
            return
        digit = first_digit(amount)
        if digit < 1 or digit > 9:
            return
        key = self._merchant_key(merchant_id)
        if self.redis:
            await self.redis.hincrby(key, str(digit), 1)
            await self.redis.hincrby(key, "total", 1)
            await self.redis.expire(key, 604800)

    async def get_merchant_stats(self, merchant_id: str) -> BenfordStats | None:
        if not self.redis:
            return None
        key = self._merchant_key(merchant_id)
        data = await self.redis.hgetall(key)
        if not data:
            return None
        counts = [int(data.get(str(d), 0)) for d in range(1, 10)]
        total = int(data.get("total", 0))
        if total < self.min_samples:
            return None
        chi2_val = benford_chi2(counts)
        return BenfordStats(
            merchant_id=merchant_id,
            observed_counts=counts,
            total_transactions=total,
            chi2_statistic=chi2_val,
            is_anomalous=chi2_val > self.critical_005,
        )

    async def evaluate(self, merchant_id: str, amount: float, is_shell_merchant: bool = False) -> FilterResult:
        start = time.perf_counter()
        triggered: list[dict] = []

        if merchant_id in self.whitelisted_merchants:
            elapsed = (time.perf_counter() - start) * 1000
            return FilterResult(action=Decision.ALLOW, stage=RuleType.BENFORD, latency_ms=round(elapsed, 3))

        await self.update_merchant_distribution(merchant_id, amount)
        stats = await self.get_merchant_stats(merchant_id)

        if stats and stats.total_transactions >= self.min_samples:
            if stats.chi2_statistic > self.critical_001 and is_shell_merchant:
                triggered.append({"name": "B-RULE-02", "severity": 5, "action": "BLOCK",
                                  "detail": f"benford_chi2_{stats.chi2_statistic:.2f}_shell"})

            if stats.chi2_statistic > self.critical_001:
                triggered.append({"name": "B-RULE-01", "severity": 4, "action": "ESCALATE",
                                  "detail": f"benford_chi2_{stats.chi2_statistic:.2f}"})

        if not triggered:
            elapsed = (time.perf_counter() - start) * 1000
            return FilterResult(action=Decision.ALLOW, stage=RuleType.BENFORD, latency_ms=round(elapsed, 3))

        has_block = any(t["action"] == "BLOCK" for t in triggered)
        max_severity = max(t["severity"] for t in triggered)
        severity_sum = sum(t["severity"] for t in triggered)

        action = Decision.BLOCK if has_block else (Decision.ESCALATE if max_severity >= 4 or severity_sum >= 7 else Decision.ALLOW)
        confidence = 1.0 if has_block else min(1.0, severity_sum / 10.0)

        elapsed = (time.perf_counter() - start) * 1000
        return FilterResult(
            action=action,
            stage=RuleType.BENFORD,
            triggered_rules=[t["name"] for t in triggered],
            rule_details=triggered,
            confidence=round(confidence, 4),
            latency_ms=round(elapsed, 3),
        )


@dataclass
class Layer1Result:
    decision: Literal["ALLOW", "ESCALATE", "BLOCK"] = Decision.ALLOW
    confidence: float = 0.0
    triggered_rules: list[str] = field(default_factory=list)
    rule_details: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    velocity_result: FilterResult | None = None
    geo_result: FilterResult | None = None
    benford_result: FilterResult | None = None


class DecisionGate:
    @staticmethod
    def compose(results: list[FilterResult]) -> FilterResult:
        all_rules = []
        all_details = []
        max_severity = 0
        severity_sum = 0

        for r in results:
            all_rules.extend(r.triggered_rules)
            all_details.extend(r.rule_details)
            for d in r.rule_details:
                sev = d.get("severity", 0)
                max_severity = max(max_severity, sev)
                severity_sum += sev

        has_block = any(d.get("action") == "BLOCK" for d in all_details)

        if has_block:
            action: Literal["ALLOW", "ESCALATE", "BLOCK"] = Decision.BLOCK
            confidence = 1.0
        elif max_severity >= 4 or severity_sum >= 7:
            action = Decision.ESCALATE
            confidence = min(1.0, severity_sum / 10.0)
        else:
            action = Decision.ALLOW
            confidence = 0.0

        total_latency = sum(r.latency_ms for r in results)
        return FilterResult(
            action=action,
            triggered_rules=all_rules,
            rule_details=all_details,
            confidence=round(confidence, 4),
            latency_ms=round(total_latency, 3),
        )


class StatisticalFilter:
    def __init__(self, redis_client=None, config: dict | None = None):
        self.redis = redis_client
        self.config = config or {}
        self.velocity = VelocityFilter(redis_client, config)
        self.geo = GeoSpatialFilter(redis_client, config)
        self.benford = BenfordFilter(redis_client, config)
        self.decision_gate = DecisionGate()
        self.shadow_mode = self.config.get("shadow_mode", False)
        self.audit_log: list[Layer1Result] = []

    async def evaluate(self, velocity_features: dict, deviation_features: dict | None = None,
                       current_loc: GeoPoint | None = None, last_loc: GeoPoint | None = None,
                       baseline: dict | None = None, account_age_days: float = 365.0,
                       user_country: str | None = None, txn_country: str | None = None,
                       merchant_id: str | None = None, amount: float = 0.0,
                       is_shell_merchant: bool = False, whitelist: set[str] | None = None) -> Layer1Result:
        import asyncio
        start = time.perf_counter()
        tasks = []

        tasks.append(self.velocity.evaluate(velocity_features, deviation_features, whitelist))

        if current_loc:
            tasks.append(self.geo.evaluate(current_loc, last_loc, baseline, account_age_days, user_country, txn_country))

        if merchant_id:
            tasks.append(self.benford.evaluate(merchant_id, amount, is_shell_merchant))

        results = await asyncio.gather(*tasks)

        composed = self.decision_gate.compose(results)

        velocity_r = results[0] if len(results) > 0 else None
        geo_r = results[1] if len(results) > 1 else None
        benford_r = results[2] if len(results) > 2 else None

        elapsed = (time.perf_counter() - start) * 1000
        layer1_result = Layer1Result(
            decision=composed.action,
            confidence=composed.confidence,
            triggered_rules=composed.triggered_rules,
            rule_details=composed.rule_details,
            latency_ms=round(elapsed, 3),
            velocity_result=velocity_r,
            geo_result=geo_r,
            benford_result=benford_r,
        )

        await self._append_audit_log(layer1_result)
        return layer1_result

    async def _append_audit_log(self, result: Layer1Result):
        self.audit_log.append(result)
        if hasattr(self.redis, "pipeline"):
            try:
                pipe = await self.redis.pipeline()
                log_key = f"layer1_audit:{result.timestamp.strftime('%Y%m%d')}"
                entry = {
                    "decision": result.decision,
                    "confidence": result.confidence,
                    "triggered_rules": result.triggered_rules,
                    "latency_ms": result.latency_ms,
                    "timestamp": result.timestamp.isoformat(),
                }
                await pipe.rpush(log_key, str(entry))
                await pipe.expire(log_key, 86400 * 30)
                await pipe.execute()
            except Exception:
                pass

    async def evaluate_shadow(self, velocity_features: dict, deviation_features: dict | None = None,
                              **kwargs) -> Layer1Result:
        result = await self.evaluate(velocity_features, deviation_features, **kwargs)
        return result
