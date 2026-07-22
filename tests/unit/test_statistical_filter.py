from datetime import datetime

import pytest

from engine.statistical_filter import StatisticalFilter, StatisticalResult
from data.features.benford import benford_expected_distribution, first_digit_frequencies, benford_chi2
from data.features.geospatial import haversine, geo_velocity_kmh


class MockFeatureStore:
    def __init__(self):
        self.velocity = {"txn_count_5min": 1, "txn_count_1h": 2, "txn_count_24h": 5}
        self.baseline = {"hourly_avg_txn_count": 1.0, "hourly_std_txn_count": 0.5, "median_amount": 500}
        self.geo = None

    def get_velocity_stats(self, user_id):
        return self.velocity

    def get_user_baseline(self, user_id):
        return self.baseline

    def get_geospatial_cache(self, user_id):
        return self.geo

    def get_merchant_amounts(self, merchant_id):
        return None


class TestStatisticalFilter:
    def setup_method(self):
        self.filter = StatisticalFilter()
        self.store = MockFeatureStore()

    def test_allows_normal_transaction(self):
        txn = {
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 500,
            "timestamp": datetime.utcnow(),
            "lat": 19.0,
            "lon": 72.0,
        }
        result = self.filter.evaluate(txn, self.store)
        assert result.decision == "ALLOW"
        assert len(result.triggered_rules) == 0

    def test_blocks_geo_impossible(self):
        self.store.geo = {"lat": 19.0, "lon": 72.0, "timestamp": 0}
        txn = {
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 500,
            "timestamp": datetime.utcnow(),
            "lat": 28.7,
            "lon": 77.1,
        }
        result = self.filter.evaluate(txn, self.store)
        assert result.decision == "BLOCK"
        assert any("geo_impossible" in r for r in result.triggered_rules)

    def test_escalates_high_velocity(self):
        self.store.velocity = {"txn_count_5min": 20, "txn_count_1h": 50, "txn_count_24h": 100}
        txn = {
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 500,
            "timestamp": datetime.utcnow(),
        }
        result = self.filter.evaluate(txn, self.store)
        assert result.decision == "ESCALATE"
        assert any("burst" in r for r in result.triggered_rules)

    def test_velocity_zscore_threshold(self):
        z = self.filter._compute_z_score(
            {"txn_count_1h": 50},
            {"hourly_avg_txn_count": 5.0, "hourly_std_txn_count": 2.0},
        )
        assert z > 3.0

    def test_benford_expected_distribution(self):
        dist = benford_expected_distribution()
        assert len(dist) == 9
        assert abs(dist.sum() - 1.0) < 0.01
        assert dist[0] > dist[8]

    def test_first_digit_frequencies(self):
        amounts = [100, 200, 300, 1000, 2500]
        freqs = first_digit_frequencies(amounts)
        assert len(freqs) == 9
        assert abs(freqs.sum() - 1.0) < 0.01
        assert freqs[0] == 2 / 5

    def test_benford_chi2_low_samples(self):
        assert benford_chi2([]) == 0.0
        assert benford_chi2([100, 200]) == 0.0

    def test_benford_chi2_returns_float(self):
        amounts = [999, 1999, 2999, 3999, 4999] * 10
        chi2_val = benford_chi2(amounts)
        assert isinstance(chi2_val, float)
        assert chi2_val > 0

    def test_haversine_distance(self):
        d = haversine(19.0760, 72.8777, 28.7041, 77.1025)
        assert 1100 < d < 1200

    def test_haversine_zero(self):
        d = haversine(19.0, 72.0, 19.0, 72.0)
        assert d == 0.0

    def test_geo_velocity_kmh(self):
        t1 = datetime(2026, 7, 22, 10, 0, 0)
        t2 = datetime(2026, 7, 22, 11, 0, 0)
        v = geo_velocity_kmh(19.0760, 72.8777, t1, 28.7041, 77.1025, t2)
        assert 1100 < v < 1200

    def test_no_rules_without_geo_cache(self):
        self.store.geo = None
        txn = {
            "user_id": "U000001",
            "merchant_id": "M00001",
            "amount": 99999,
            "timestamp": datetime.utcnow(),
            "lat": 28.7,
            "lon": 77.1,
        }
        result = self.filter.evaluate(txn, self.store)
        assert result.decision in ("ALLOW", "ESCALATE")


class TestStatisticalResult:
    def test_dataclass_defaults(self):
        r = StatisticalResult(decision="ALLOW", triggered_rules=[])
        assert r.decision == "ALLOW"
        assert r.triggered_rules == []
        assert r.velocity_stats is None
        assert r.benford_chi2 is None
