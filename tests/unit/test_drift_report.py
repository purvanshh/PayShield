import time

import pytest

from observability.drift_report import (
    DRIFT_PREFIX,
    WINDOW_SECONDS,
    compute_psi_report,
    interpret_psi,
)


class TestInterpretPsi:
    def test_thresholds(self):
        assert interpret_psi(0.05) == "STABLE"
        assert interpret_psi(0.15) == "MODERATE"
        assert interpret_psi(0.5) == "DRIFT"


@pytest.mark.asyncio
class TestComputePsiReport:
    @pytest.fixture()
    def redis(self):
        from tests.fake_redis import FakeRedis

        return FakeRedis()

    async def _seed(self, redis, key, values, timestamps, offset=0):
        for i, (value, ts) in enumerate(zip(values, timestamps, strict=True), start=offset):
            member = f"{i}:{value}"
            await redis.zadd(f"{DRIFT_PREFIX}{key}", {member: ts})

    async def test_no_data_returns_empty(self, redis):
        report = await compute_psi_report(redis)
        assert report["features"] == {}
        assert report["status"] == "NO_DRIFT_DETECTED"
        assert report["generated_at"].endswith("+00:00")

    async def test_insufficient_data(self, redis):
        now = time.time()
        await self._seed(redis, "txn_count_5m", [1.0], [now - 0.1])
        report = await compute_psi_report(redis)
        entry = report["features"]["txn_count_5m"]
        assert entry["status"] == "INSUFFICIENT_DATA"
        assert entry["psi"] is None
        assert report["status"] == "NO_DRIFT_DETECTED"

    async def test_stable_distributions(self, redis):
        now = time.time()
        old_ts = now - 1.5 * WINDOW_SECONDS
        new_ts = now - 0.5 * WINDOW_SECONDS
        await self._seed(redis, "txn_count_5m", [5.0] * 20, [old_ts] * 20)
        await self._seed(redis, "txn_count_5m", [5.0] * 20, [new_ts] * 20, offset=20)
        report = await compute_psi_report(redis)
        entry = report["features"]["txn_count_5m"]
        assert entry["status"] == "STABLE"
        assert report["status"] == "NO_DRIFT_DETECTED"

    async def test_drifted_distributions(self, redis):
        now = time.time()
        old_ts = now - 1.5 * WINDOW_SECONDS
        new_ts = now - 0.5 * WINDOW_SECONDS
        await self._seed(redis, "amount_total_1h", [10 + i % 25 for i in range(25)], [old_ts] * 25)
        await self._seed(redis, "amount_total_1h", [970 + i % 25 for i in range(25)], [new_ts] * 25, offset=25)
        report = await compute_psi_report(redis)
        entry = report["features"]["amount_total_1h"]
        assert entry["psi"] is not None
        assert entry["status"] == "DRIFT"
        assert "amount_total_1h" in report["drifted_features"]
        assert report["status"] == "DRIFT_DETECTED"

    async def test_constant_identical_series_is_stable(self, redis):
        now = time.time()
        old_ts = now - 1.5 * WINDOW_SECONDS
        new_ts = now - 0.5 * WINDOW_SECONDS
        await self._seed(redis, "txn_count_1h", [3.0] * 20, [old_ts] * 20)
        await self._seed(redis, "txn_count_1h", [3.0] * 20, [new_ts] * 20, offset=20)
        entry = (await compute_psi_report(redis))["features"]["txn_count_1h"]
        assert entry["status"] == "STABLE"

    async def test_malformed_members_skipped(self, redis):
        now = time.time()
        await redis.zadd(f"{DRIFT_PREFIX}txn_count_1h", {"garbage": now - 0.5 * WINDOW_SECONDS})
        await redis.zadd(f"{DRIFT_PREFIX}txn_count_1h", {"7:5.0": now - 0.5 * WINDOW_SECONDS})
        report = await compute_psi_report(redis)
        entry = report["features"]["txn_count_1h"]
        assert entry["status"] == "INSUFFICIENT_DATA"
        assert entry["expected_samples"] == 0
        assert entry["actual_samples"] == 1

    async def test_timestamp_only_actual_bucket(self, redis):
        now = time.time()
        await self._seed(redis, "device_txn_count_24h", [2.0] * 20, [now - 0.1] * 20)
        report = await compute_psi_report(redis)
        assert report["features"]["device_txn_count_24h"]["status"] == "INSUFFICIENT_DATA"
