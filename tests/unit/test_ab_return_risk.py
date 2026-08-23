"""Return-risk A/B experiment tests (Phase 38)."""

from ml.ab_testing import ReturnRiskABExperiment
from tests.fake_redis import FakeRedis

CHAMPION = {
    "user_return_rate_30d": 0.25,
    "user_serial_returner_flag": 0.20,
    "merchant_return_rate_30d": 0.15,
    "txn_category_return_baseline": 0.15,
    "txn_amount_risk": 0.10,
    "user_cod_refusal_rate": 0.10,
    "user_return_velocity_7d": 0.05,
}

CHALLENGER = {**CHAMPION, "user_return_rate_30d": 0.30, "txn_amount_risk": 0.05}


class TestReturnRiskABExperiment:
    async def test_create_and_fetch_round_trip(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_t1")
        data = await exp.create_experiment(CHAMPION, CHALLENGER, traffic_split=0.10)
        assert data["status"] == "running"
        fetched = await exp.get_experiment()
        assert fetched["champion"]["weights"] == CHAMPION
        assert fetched["challenger"]["traffic_pct"] == 0.10

    async def test_bucketing_is_deterministic_per_merchant(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_t2")
        await exp.create_experiment(CHAMPION, CHALLENGER, traffic_split=0.10)
        results = [await exp.get_weights_for_request(f"M_{i}") for i in range(200)]
        # every merchant stays deterministic; ~10% land on the challenger
        challenger_count = sum(1 for w in results if w == CHALLENGER)
        assert 5 <= challenger_count <= 25
        # same merchant twice -> same arm
        assert await exp.get_weights_for_request("M_42") == await exp.get_weights_for_request("M_42")

    async def test_no_active_experiment_uses_defaults(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_missing")
        weights = await exp.get_weights_for_request("M_1")
        assert weights == CHAMPION  # defaults match the shipped registry

    async def test_evaluate_promotes_better_challenger(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_t3")
        await exp.create_experiment(CHAMPION, CHALLENGER)
        out = await exp.evaluate_experiment(
            outcomes={
                "champion": [1, 0, 0, 0, 0],
                "challenger": [1, 1, 1, 1, 0],
            }
        )
        assert out["champion_precision"] == 0.2
        assert out["challenger_precision"] == 0.8
        assert out["improvement"] == 0.6
        assert out["significant"] is True
        assert out["recommendation"] == "promote"

    async def test_evaluate_keeps_worse_challenger(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_t4")
        await exp.create_experiment(CHAMPION, CHALLENGER)
        out = await exp.evaluate_experiment(
            outcomes={"champion": [1, 1], "challenger": [0, 0]}
        )
        assert out["recommendation"] == "keep"

    async def test_traffic_counters_increment(self):
        redis = FakeRedis()
        exp = ReturnRiskABExperiment(redis, "rr_exp_t5")
        await exp.create_experiment(CHAMPION, CHALLENGER, traffic_split=0.5)
        for i in range(20):
            await exp.get_weights_for_request(f"M_{i}")
        traffic = await redis.hgetall("ab:return_risk:rr_exp_t5:traffic")
        assert int(traffic["champion_requests"]) + int(traffic["challenger_requests"]) == 20
