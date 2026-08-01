# ruff: noqa: ARG002 -- test doubles mirror the client interface


from data.features.benford import (
    benford_chi2,
    benford_expected_distribution,
    first_digit_frequencies,
)
from data.features.geospatial import geo_velocity_kmh, haversine
from data.features.velocity import VelocityComputer


class MockFeatureStore:
    def __init__(self):
        self.zcount_values = 0
        self.baseline = None

    def zcount(self, key, min_s, max_s):
        return self.zcount_values

    def get_user_baseline(self, user_id):
        return self.baseline


class TestVelocityComputer:
    def test_zscore_no_baseline(self):
        store = MockFeatureStore()
        vc = VelocityComputer(store)
        assert vc.z_score("U1") == 0.0

    def test_zscore_with_std_zero(self):
        store = MockFeatureStore()
        store.baseline = {"daily_avg_txn_count": 10, "daily_std_txn_count": 0}
        vc = VelocityComputer(store)
        assert vc.z_score("U1") == 0.0

    def test_zscore_normal(self):
        store = MockFeatureStore()
        store.zcount_values = 20
        store.baseline = {"daily_avg_txn_count": 10, "daily_std_txn_count": 5}
        vc = VelocityComputer(store)
        assert vc.z_score("U1") == 2.0

    def test_count_last_hour(self):
        store = MockFeatureStore()
        store.zcount_values = 5
        vc = VelocityComputer(store)
        assert vc.count_last_hour("U1") == 5

    def test_count_last_5min(self):
        store = MockFeatureStore()
        store.zcount_values = 3
        vc = VelocityComputer(store)
        assert vc.count_last_5min("U1") == 3

    def test_count_last_24h(self):
        store = MockFeatureStore()
        store.zcount_values = 25
        vc = VelocityComputer(store)
        assert vc.count_last_24h("U1") == 25


class TestGeospatial:
    def test_haversine_mumbai_delhi(self):
        d = haversine(19.0760, 72.8777, 28.7041, 77.1025)
        assert 1100 < d < 1200

    def test_haversine_same_point(self):
        assert haversine(12.97, 77.59, 12.97, 77.59) == 0.0

    def test_haversine_commutative(self):
        d1 = haversine(19.0, 72.0, 28.0, 77.0)
        d2 = haversine(28.0, 77.0, 19.0, 72.0)
        assert abs(d1 - d2) < 0.01

    def test_geo_velocity_zero_time(self):
        from datetime import datetime
        t = datetime.utcnow()
        v = geo_velocity_kmh(19.0, 72.0, t, 19.0, 72.0, t)
        assert v == 0.0


class TestBenford:
    def test_expected_sum_to_one(self):
        dist = benford_expected_distribution()
        assert abs(dist.sum() - 1.0) < 0.01

    def test_first_digit_empty(self):
        f = first_digit_frequencies([])
        assert (f == 0).all()

    def test_first_digit_known(self):
        f = first_digit_frequencies([100, 200, 300, 1, 5000, 9999])
        assert abs(f.sum() - 1.0) < 0.01
        assert f[0] > 0

    def test_benford_chi2_zero_for_small_sample(self):
        assert benford_chi2([100]) == 0.0
        assert benford_chi2([100, 200]) == 0.0

    def test_benford_chi2_large_sample(self):
        amounts = [999] * 50
        c = benford_chi2(amounts)
        assert c > 0
