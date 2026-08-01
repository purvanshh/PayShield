

from engine.statistical_filter import (
    BENFORD_EXPECTED,
    FilterResult,
    GeoPoint,
    GeoSpatialFilter,
    Layer1Result,
    StatisticalFilter,
    VelocityFilter,
    benford_chi2,
    first_digit,
    geo_velocity_kmh,
    haversine,
)


class TestGeoFunctions:
    def test_haversine_distance(self):
        d = haversine(19.0760, 72.8777, 28.7041, 77.1025)
        assert 1100 < d < 1200

    def test_haversine_zero(self):
        d = haversine(19.0, 72.0, 19.0, 72.0)
        assert d == 0.0

    def test_geo_velocity_kmh(self):
        loc1 = GeoPoint(lat=19.0760, lon=72.8777, timestamp=1000)
        loc2 = GeoPoint(lat=28.7041, lon=77.1025, timestamp=4600)
        v = geo_velocity_kmh(loc1, loc2)
        assert 1100 < v < 1200

    def test_first_digit(self):
        assert first_digit(100) == 1
        assert first_digit(2500) == 2
        assert first_digit(999) == 9


class TestBenford:
    def test_benford_expected_length(self):
        assert len(BENFORD_EXPECTED) == 9
        assert BENFORD_EXPECTED[0] > BENFORD_EXPECTED[8]

    def test_benford_chi2_empty(self):
        assert benford_chi2([]) == 0.0

    def test_benford_chi2_low_samples(self):
        counts = [1, 0, 0, 0, 0, 0, 0, 0, 0]
        val = benford_chi2(counts)
        assert isinstance(val, float)

    def test_benford_chi2_returns_float(self):
        counts = [5, 4, 3, 3, 2, 2, 1, 1, 1]
        val = benford_chi2(counts)
        assert isinstance(val, float)


class TestVelocityFilter:
    def setup_method(self):
        self.filter = VelocityFilter(redis_client=None, config={})

    async def test_allows_low_velocity(self):
        vf = {"txn_count_5m": 1, "txn_count_1h": 2, "txn_count_24h": 5, "amount_total_1h": 500.0}
        result = await self.filter.evaluate(vf, {"baseline_txn_count_24h": 999})
        assert result.action in ("ALLOW",)

    async def test_blocks_burst(self):
        vf = {"txn_count_5m": 20, "txn_count_1h": 50, "txn_count_24h": 100,
              "amount_total_1h": 5000.0, "device_txn_count_24h": 1, "distinct_users_last_24h": 1,
              "ip_txn_count_5m": 1, "distinct_merchants_1h": 1}
        result = await self.filter.evaluate(vf, {"baseline_txn_count_24h": 2})
        assert result.action == "BLOCK"
        assert "V-RULE-01" in result.triggered_rules

    async def test_escalates_zscore(self):
        vf = {"txn_count_5m": 1, "txn_count_1h": 2, "txn_count_24h": 5,
              "amount_total_1h": 500.0, "device_txn_count_24h": 1, "distinct_users_last_24h": 1,
              "ip_txn_count_5m": 1, "distinct_merchants_1h": 12}
        result = await self.filter.evaluate(vf, {"amount_z_score": 5.0})
        assert result.action == "ESCALATE"
        assert "V-RULE-02" in result.triggered_rules
        assert "V-RULE-06" in result.triggered_rules

    async def test_single_low_severity_rule_stays_allow(self):
        vf = {"txn_count_5m": 1, "txn_count_1h": 2, "txn_count_24h": 5,
              "amount_total_1h": 500.0, "device_txn_count_24h": 1, "distinct_users_last_24h": 1,
              "ip_txn_count_5m": 1, "distinct_merchants_1h": 1}
        result = await self.filter.evaluate(vf, {"amount_z_score": 5.0})
        assert "V-RULE-02" in result.triggered_rules
        assert result.action == "ALLOW"


class TestGeoSpatialFilter:
    def setup_method(self):
        self.filter = GeoSpatialFilter(redis_client=None, config={})

    async def test_allows_same_location(self):
        loc = GeoPoint(lat=19.076, lon=72.877, timestamp=1000)
        result = await self.filter.evaluate(loc, None)
        assert result.action == "ALLOW"

    async def test_blocks_impossible_travel(self):
        last = GeoPoint(lat=19.076, lon=72.877, timestamp=1000)
        current = GeoPoint(lat=28.704, lon=77.102, timestamp=1100)
        result = await self.filter.evaluate(current, last)
        assert result.action == "BLOCK"
        assert "G-RULE-01" in result.triggered_rules


class TestStatisticalFilter:
    def setup_method(self):
        self.filter = StatisticalFilter(config={})

    async def test_allows_normal_transaction(self):
        vf = {"txn_count_5m": 1, "txn_count_1h": 2, "txn_count_24h": 5, "amount_total_1h": 500.0,
              "device_txn_count_24h": 1, "distinct_users_last_24h": 1, "ip_txn_count_5m": 1,
              "distinct_merchants_1h": 1}
        result = await self.filter.evaluate(vf, merchant_id="M00001", amount=500.0)
        assert result.decision in ("ALLOW",)

    async def test_blocks_high_velocity(self):
        vf = {"txn_count_5m": 20, "txn_count_1h": 50, "txn_count_24h": 100, "amount_total_1h": 5000.0,
              "device_txn_count_24h": 1, "distinct_users_last_24h": 1, "ip_txn_count_5m": 1,
              "distinct_merchants_1h": 1}
        result = await self.filter.evaluate(vf, {"baseline_txn_count_24h": 2}, merchant_id="M00001", amount=500.0)
        assert result.decision in ("BLOCK", "ESCALATE")


class TestFilterResult:
    def test_dataclass_defaults(self):
        r = FilterResult()
        assert r.action == "ALLOW"
        assert r.triggered_rules == []
        assert r.confidence == 0.0

    def test_layer1_result_defaults(self):
        r = Layer1Result()
        assert r.decision == "ALLOW"
        assert r.triggered_rules == []
        assert r.confidence == 0.0
