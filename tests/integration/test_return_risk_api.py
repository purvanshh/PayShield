"""Return-risk API integration tests (Phase 16)."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
DEV_KEY = "payshield-dev-key-2026"


@pytest.fixture
async def client():
    app.state.resources = {"redis": FakeRedis()}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


async def _seed_serial_returner(redis):
    import time

    end = time.time()
    await redis.hmset(
        "return_risk:user:U003",
        {
            "total_orders": "18",
            "total_returns": "10",
            "return_rate_30d": "0.62",
            "return_rate_90d": "0.55",
            "avg_return_value": "3800",
            "cod_refusals": "3",
            "cod_orders": "7",
            "return_reason_distribution": json.dumps({"SIZE_ISSUE": 5, "CHANGED_MIND": 5}),
        },
    )
    await redis.hmset(
        "return_risk:merchant:M001",
        {"return_rate_30d": "0.28", "avg_resolution_hours": "26.5", "return_fraud_rate": "0.03"},
    )
    await redis.zadd("return_risk:merchant:M001:category", {"fashion": 0.35})
    await redis.zadd("return_risk:user:U003:returns", {"ORD_1": end - 86400, "ORD_2": end - 2 * 86400})


class TestReturnRiskAuth:
    async def test_score_requires_auth(self, client):
        resp = await client.post("/v1/return/score", json={})
        assert resp.status_code == 403

    async def test_profile_requires_auth(self, client):
        resp = await client.get("/v1/return/profile/U001")
        assert resp.status_code == 403


class TestReturnRiskScore:
    async def test_scores_seeded_profile(self, client):
        app.state.resources["redis"] = FakeRedis()
        await _seed_serial_returner(app.state.resources["redis"])
        body = {
            "order_id": "ORD_9",
            "user_id": "U003",
            "merchant_id": "M001",
            "amount": "6000",
            "currency": "INR",
            "category": "fashion",
            "payment_method": "UPI",
            "cod_flag": True,
        }
        resp = await client.post("/v1/return/score", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        payload = data["data"]
        assert payload["order_id"] == "ORD_9"
        assert payload["risk_tier"] == "HIGH"
        assert "user_return_rate_30d" in payload["feature_breakdown"]
        assert any(r["rule_id"] == "R-RULE-01" and r["triggered"] for r in payload["rules_triggered"])
        assert any("prepaid" in r.lower() for r in payload["recommendations"])
        assert payload["user_profile"]["total_orders"] == 18

    async def test_scores_new_user_defaults(self, client):
        app.state.resources["redis"] = FakeRedis()
        body = {
            "order_id": "ORD_1",
            "user_id": "U_NEW",
            "merchant_id": "M_X",
            "amount": "1200",
            "currency": "INR",
            "category": "grocery",
            "payment_method": "UPI",
            "cod_flag": False,
        }
        resp = await client.post("/v1/return/score", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["risk_tier"] in ("LOW", "MEDIUM")
        assert payload["confidence"] < 1.0
        assert payload["user_profile"]["is_new_user"] is True

    async def test_score_validation_amount(self, client):
        app.state.resources["redis"] = FakeRedis()
        body = {
            "order_id": "ORD_2",
            "user_id": "U001",
            "merchant_id": "M001",
            "amount": "-5",
            "category": "fashion",
            "cod_flag": False,
        }
        resp = await client.post("/v1/return/score", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 422


class TestReturnRiskUpdate:
    async def test_update_refreshes_profile(self, client):
        app.state.resources["redis"] = FakeRedis()
        body = {
            "user_id": "U010",
            "order_id": "ORD_77",
            "amount": "1500",
            "category": "fashion",
            "cod_flag": True,
            "returned": True,
            "return_reason": "SIZE_ISSUE",
        }
        resp = await client.post("/v1/return/update", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "updated"
        profile = await app.state.resources["redis"].hgetall("return_risk:user:U010")
        assert int(profile["total_returns"]) == 1
        assert int(profile["cod_orders"]) == 1

    async def test_update_validates_returned(self, client):
        app.state.resources["redis"] = FakeRedis()
        body = {"user_id": "U011", "order_id": "ORD_78", "amount": "100", "returned": False}
        resp = await client.post("/v1/return/update", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        profile = await app.state.resources["redis"].hgetall("return_risk:user:U011")
        assert int(profile["total_orders"]) == 1
        assert "total_returns" not in profile


class TestReturnRiskProfile:
    async def test_profile_known_user(self, client):
        app.state.resources["redis"] = FakeRedis()
        await _seed_serial_returner(app.state.resources["redis"])
        resp = await client.get("/v1/return/profile/U003", headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "U003"
        assert data["serial_returner"] is True
        assert data["total_orders"] == 18

    async def test_profile_new_user(self, client):
        app.state.resources["redis"] = FakeRedis()
        resp = await client.get("/v1/return/profile/U999", headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        assert resp.json()["is_new_user"] is True


class TestReturnRiskExplain:
    async def test_explain_requires_auth(self, client):
        resp = await client.post("/v1/return/explain", json={})
        assert resp.status_code == 403

    async def test_explain_returns_waterfall(self, client):
        app.state.resources["redis"] = FakeRedis()
        await _seed_serial_returner(app.state.resources["redis"])
        body = {
            "order_id": "ORD_XPL",
            "user_id": "U003",
            "merchant_id": "M001",
            "amount": "6000",
            "category": "fashion",
            "payment_method": "UPI",
            "cod_flag": True,
        }
        resp = await client.post("/v1/return/explain", json=body, headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == "ORD_XPL"
        assert 0 <= data["return_risk_score"] <= 1
        assert data["risk_tier"] in ("LOW", "MEDIUM", "HIGH")
        assert data["base_score"] == 0.5
        assert data["note"]
        assert len(data["waterfall"]) >= 7  # all model features attributed
        # contributions must be in [0, importance] after normalisation
        for item in data["waterfall"]:
            assert item["feature"]
            assert 0 <= item["contribution"] <= 1
            assert item["importance"] >= 0
        # sorted descending by contribution
        contribs = [c["contribution"] for c in data["waterfall"]]
        assert contribs == sorted(contribs, reverse=True)

    async def test_explain_does_not_mutate_redis(self, client):
        app.state.resources["redis"] = FakeRedis()
        await _seed_serial_returner(app.state.resources["redis"])
        body = {
            "order_id": "ORD_XPL2",
            "user_id": "U003",
            "merchant_id": "M001",
            "amount": "6000",
            "category": "fashion",
            "payment_method": "UPI",
            "cod_flag": True,
        }
        before = await app.state.resources["redis"].hgetall("return_risk:user:U003")
        await client.post("/v1/return/explain", json=body, headers={"X-API-Key": DEV_KEY})
        after = await app.state.resources["redis"].hgetall("return_risk:user:U003")
        assert before == after
