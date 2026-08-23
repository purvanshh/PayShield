"""Return-risk drift monitor tests (Phase 39)."""

import time

import numpy as np

from observability.return_risk_drift import (
    ReturnRiskDriftMonitor,
    record_return_risk_samples,
)
from tests.fake_redis import FakeRedis

FEATURE = "user_return_rate_30d"
KEY = f"return_risk:drift:{FEATURE}"


async def _seed(redis, baseline_values, current_values):
    """Slot baseline samples 1-30d old and current samples inside 24h."""
    now = time.time()
    for i, value in enumerate(baseline_values):
        await redis.zadd(KEY, {f"{(now - (i + 2) * 86400):.0f}:{value}": now - (i + 2) * 86400})
    for i, value in enumerate(current_values):
        await redis.zadd(KEY, {f"{(now - i * 100):.0f}:{value}": now - i * 100})


class TestRecordSampling:
    async def test_records_numeric_features_only(self):
        redis = FakeRedis()
        breakdown = {
            "user_return_rate_30d": {"value": 0.35},
            "txn_amount_risk": {"value": 0.55},
            "user_serial_returner_flag": {"value": True},  # bool - skipped
            "txn_cod_flag": {"value": False},
        }
        await record_return_risk_samples(redis, breakdown)
        assert await redis.zcount(KEY, 0, float("inf")) == 1
        assert await redis.zcount("return_risk:drift:txn_amount_risk", 0, float("inf")) == 1
        assert await redis.zcount("return_risk:drift:user_serial_returner_flag", 0, float("inf")) == 0

    async def test_corrupt_pipe_is_swallowed(self):
        class BrokenPipeline:
            async def zadd(self, *a, **k):
                return self

            async def zremrangebyscore(self, *a, **k):
                return self

            async def execute(self):
                raise ConnectionError("down")

        class BrokenRedis:
            async def pipeline(self):
                return BrokenPipeline()

        await record_return_risk_samples(BrokenRedis(), {"user_return_rate_30d": {"value": 0.2}})
        # no raise


class TestDriftMonitor:
    async def test_stable_distribution(self):
        redis = FakeRedis()
        rng = np.random.default_rng(7)
        # identical series in both windows -> no observable shift -> PSI ~ 0
        stable = (0.30 + rng.normal(0, 0.02, 40)).tolist()
        await _seed(redis, stable, list(stable))
        report = await ReturnRiskDriftMonitor(redis, [FEATURE]).check()
        assert report["features"][FEATURE]["psi"] < 0.10
        assert report["overall_status"] == "STABLE"

    async def test_shifted_distribution_detects_drift(self):
        redis = FakeRedis()
        rng = np.random.default_rng(7)
        await _seed(
            redis,
            (0.10 + rng.normal(0, 0.02, 40)).tolist(),
            (0.90 + rng.normal(0, 0.02, 40)).tolist(),
        )
        report = await ReturnRiskDriftMonitor(redis, [FEATURE]).check()
        assert report["features"][FEATURE]["status"] == "DRIFT"
        assert report["overall_status"] == "DRIFT"

    async def test_missing_data_is_stable(self):
        redis = FakeRedis()
        report = await ReturnRiskDriftMonitor(redis, [FEATURE]).check()
        assert report["overall_status"] == "STABLE"
        assert report["features"][FEATURE]["psi"] == 0.0

    async def test_broken_redis_degrades_silently(self):
        class BrokenRedis:
            async def zrangebyscore(self, *a, **k):
                raise ConnectionError("down")

        report = await ReturnRiskDriftMonitor(BrokenRedis(), [FEATURE]).check()
        assert report["features"][FEATURE]["psi"] == 0.0

    async def test_full_report_shape(self):
        redis = FakeRedis()
        await _seed(redis, [0.2] * 30, [0.2] * 30)
        report = await ReturnRiskDriftMonitor(redis).check()
        assert len(report["features"]) == 6
        assert set(report.keys()) == {"timestamp", "features", "overall_status"}
