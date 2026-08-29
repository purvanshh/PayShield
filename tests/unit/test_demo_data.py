"""Demo data seeder tests (Phase 22)."""

import asyncio
import json
import time
from decimal import Decimal

from scripts.seed_demo_data import seed_demo_data
from store.audit_log import AuditLogReader
from tests.fake_redis import FakeSyncRedis


class TestDemoDataSeeder:
    def setup_method(self):
        self.redis = FakeSyncRedis()

    def test_seeds_return_risk_profiles(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        serial = self.redis.hgetall("return_risk:user:U_SERIAL_001")
        assert int(serial["total_orders"]) == 15
        assert int(serial["total_returns"]) == 10
        assert serial["serial_returner"] == "true"

        honest = self.redis.hgetall("return_risk:user:U_HONEST_001")
        assert int(honest["total_orders"]) == 25

    def test_seeds_velocity_zsets(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        out = self.redis.zrangebyscore(
            "return_risk:user:U_SERIAL_001:returns", 0, float("inf")
        )
        assert len(out) == 3

    def test_seeds_device_index_and_sharing(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        device = self.redis.hgetall("dfp:DEV_CLEAN_001")
        assert device["user_id"] == "U_CLEAN_001"
        assert json.loads(device["features"])[0].startswith("ip:")
        assert self.redis.smembers("ud:DEV_SHARED_001") == {"U_FRAUD_001", "U_RING_001", "U_RING_002"}

    def test_seeds_merchant_baselines(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        assert self.redis.hgetall("return_risk:merchant:M_FASHION_001")["return_rate_30d"] == "0.30"
        assert self.redis.zscore("return_risk:merchant:M_ELECTRONICS_001:category", "electronics") == 0.12

    def test_seeds_velocity_histories(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        clean = self.redis.lrange("velocity:user:U_CLEAN_001", 0, -1)
        assert len(clean) == 3
        suspicious = self.redis.lrange("velocity:user:U_FRAUD_001", 0, -1)
        assert len(suspicious) == 12
        events = [json.loads(e) for e in suspicious]
        assert all(e["amount"] == 95000.0 for e in events)

    def test_reseeding_resets_velocity_history(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        # simulate accumulation from repeated /v1/score calls on the live path
        stale = json.dumps(
            {
                "ts": time.time() - 300,
                "amount": 2500.0,
                "merchant": "M_FASHION_001",
                "user": "U_CLEAN_001",
                "device": "DEV_CLEAN_001",
            }
        )
        self.redis.lpush("velocity:user:U_CLEAN_001", stale)
        self.redis.set("velocity:dedup:TXN_LIVE_CLEAN", "1")
        assert len(self.redis.lrange("velocity:user:U_CLEAN_001", 0, -1)) == 4

        seed_demo_data(redis=self.redis, audit_writer=None)
        clean = self.redis.lrange("velocity:user:U_CLEAN_001", 0, -1)
        assert len(clean) == 3  # reset to the exact curated scenario
        assert self.redis.get("velocity:dedup:TXN_LIVE_CLEAN") is None

    def test_seeds_audit_chain(self, tmp_path):
        from store.audit_log import AuditLogWriter

        writer = AuditLogWriter(str(tmp_path))
        seed_demo_data(redis=self.redis, audit_writer=writer)
        reader = AuditLogReader(str(tmp_path))

        clean = reader.get_transaction("TXN_CLEAN_001")
        assert clean is not None
        assert clean["payload"]["amount"] == 2500.0
        assert clean["payload"]["triggered_rules"] == []

        weak = reader.get_transaction("TXN_NEW_001")
        assert weak is not None
        assert weak["payload"]["txn_id"] == "TXN_NEW_001"
        assert "device_fingerprint" not in weak["payload"]

    def test_seeds_benford_distribution(self):
        seed_demo_data(redis=self.redis, audit_writer=None)
        benford = self.redis.hgetall("benford:M_FASHION_001")
        assert int(benford["total"]) == 101
        assert int(benford["1"]) == 30

    def test_seeded_abuse_ring_triggers_sentinel(self):
        from return_risk.feature_engine import ReturnRiskFeatureEngine
        from return_risk.rules_engine import RulesEngine
        from return_risk.scorer import ReturnRiskScorer

        seed_demo_data(redis=self.redis, audit_writer=None)
        scorer = ReturnRiskScorer(
            feature_engine=ReturnRiskFeatureEngine(self.redis),
            rules_engine=RulesEngine(),
        )

        async def score_ring(uid):
            return await scorer.score(
                user_id=uid,
                merchant_id="M_FASHION_001",
                order_id=f"ORD_{uid}",
                amount=Decimal("5000"),
                category="fashion",
                cod_flag=False,
                payment_method="UPI",
                shipping_address="560037",
            )

        # Populate the shared-address set (A, B, C ship to 560037 first).
        for uid in ("U_RING_001", "U_RING_002", "U_RING_003"):
            asyncio.run(score_ring(uid))
        # 4th user on the shared address -> count == 4 -> R-RULE-09 fires.
        result = asyncio.run(score_ring("U_RING_004"))
        assert any(
            r["rule_id"] == "R-RULE-09" and r["triggered"] for r in result["rules_triggered"]
        )
        assert result["risk_tier"] == "HIGH"
        assert result["return_risk_score"] >= 0.85
