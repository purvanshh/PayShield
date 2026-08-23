"""P9 security & performance API tests: CORS, per-key rate limiting,
refresh-token rotation, TOTP endpoints, investigations batching, graph pagination."""

import json
import time
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

import api.dependencies as dependencies
from api.auth import TOTPManager
from api.main import app
from engine.ensemble import EnsembleFusionEngine
from engine.statistical_filter import StatisticalFilter
from store.graph_db import NetworkXGraphDB
from tests.fake_redis import FakeRedis

BASE_URL = "http://test"
DEV_KEY = "payshield-dev-key-2026"


@pytest.fixture
async def client():
    app.state.resources = {
        "redis": FakeRedis(),
        "statistical_filter": StatisticalFilter(),
        "ensemble": EnsembleFusionEngine(),
        "graph_db": NetworkXGraphDB(),
        "graph_writer": None,
        "l2_inference": None,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


class TestCORS:
    async def test_preflight_allowed_origin(self, client):
        resp = await client.options(
            "/v1/score",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    async def test_preflight_unauthorized_origin_rejected(self, client):
        resp = await client.options(
            "/v1/score",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-origin" not in resp.headers

    async def test_no_wildcard_origin(self):
        assert "*" not in [o for o in app.user_middleware if "CORS" in str(o)]
        from fastapi.middleware.cors import CORSMiddleware
        cors_kwargs = None
        for mw in app.user_middleware:
            if mw.cls is CORSMiddleware:
                cors_kwargs = mw.kwargs
        assert cors_kwargs is not None
        assert "*" not in cors_kwargs["allow_origins"]


class TestRateLimiting:
    async def test_429_after_per_key_limit(self, client, monkeypatch):
        monkeypatch.setattr(dependencies, "API_KEY_RATE_LIMIT", 5)
        headers = {"X-API-Key": DEV_KEY}
        for i in range(5):
            resp = await client.get("/v1/investigations", headers=headers)
            assert resp.status_code == 200
        resp = await client.get("/v1/investigations", headers=headers)
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Rate limit exceeded"
        assert resp.headers.get("retry-after") == "3600"

    async def test_429_after_per_user_limit(self, client, monkeypatch):
        monkeypatch.setattr(dependencies, "USER_RATE_LIMIT", 2)
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200
        access = login.json()["access_token"]
        bearer = {"Authorization": f"Bearer {access}"}
        for i in range(2):
            resp = await client.get("/v1/investigations", headers=bearer)
            assert resp.status_code == 200
        resp = await client.get("/v1/investigations", headers=bearer)
        assert resp.status_code == 429

    async def test_different_keys_not_limited_together(self, client, monkeypatch):
        monkeypatch.setattr(dependencies, "API_KEY_RATE_LIMIT", 5)
        auth = dependencies.auth_manager
        auth.register_api_key("psk-test-key-2", role="system", name="t2")
        headers2 = {"X-API-Key": "psk-test-key-2"}
        resp = await client.get("/v1/investigations", headers=headers2)
        assert resp.status_code == 200

    async def test_limit_constant_is_1000_per_hour(self):
        assert dependencies.API_KEY_RATE_LIMIT == 1000
        assert dependencies.USER_RATE_LIMIT == 1000
        assert dependencies.RATE_LIMIT_WINDOW_SECONDS == 3600


class TestRefreshRotation:
    async def test_refresh_rotates_and_old_token_dies(self, client):
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200
        first_refresh = login.json()["refresh_token"]

        resp1 = await client.post("/v1/auth/refresh", json={"refresh_token": first_refresh})
        assert resp1.status_code == 200
        second_refresh = resp1.json()["refresh_token"]
        assert second_refresh != first_refresh

        resp_old = await client.post("/v1/auth/refresh", json={"refresh_token": first_refresh})
        assert resp_old.status_code == 401

        resp_new = await client.post("/v1/auth/refresh", json={"refresh_token": second_refresh})
        assert resp_new.status_code == 200

    async def test_invalid_refresh_rejected(self, client):
        resp = await client.post("/v1/auth/refresh", json={"refresh_token": "garbage-token"})
        assert resp.status_code == 401

    async def test_refresh_window_is_seven_days(self, client):
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        refresh_token = login.json()["refresh_token"]
        import jwt
        payload = jwt.decode(refresh_token, dependencies.auth_manager.secret, algorithms=["HS256"])
        assert payload["exp"] - payload["iat"] == 7 * 24 * 3600


class TestTOTPEndpoints:
    async def test_setup_requires_admin(self, client):
        resp = await client.post(
            "/v1/auth/totp/setup",
            json={"username": "admin"},
            headers={"X-API-Key": DEV_KEY},
        )
        assert resp.status_code == 403

    async def test_setup_and_verify_flow(self, client):
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        access = login.json()["access_token"]
        bearer = {"Authorization": f"Bearer {access}"}

        setup = await client.post("/v1/auth/totp/setup", json={"username": "admin"}, headers=bearer)
        assert setup.status_code == 200
        secret = setup.json()["secret"]
        assert setup.json()["otpauth_uri"].startswith("otpauth://totp/")

        code = TOTPManager(secret).current_code()
        verify = await client.post("/v1/auth/totp/verify", json={"username": "admin", "code": code}, headers=bearer)
        assert verify.status_code == 200
        assert verify.json() == {"verified": True, "enabled": True}

    async def test_wrong_totp_code_rejected(self, client):
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        access = login.json()["access_token"]
        bearer = {"Authorization": f"Bearer {access}"}
        setup = await client.post("/v1/auth/totp/setup", json={"username": "admin"}, headers=bearer)
        secret = setup.json()["secret"]
        code = TOTPManager(secret).current_code()
        wrong = str((int(code) + 1) % 1_000_000).zfill(6)
        verify = await client.post("/v1/auth/totp/verify", json={"username": "admin", "code": wrong}, headers=bearer)
        assert verify.json()["verified"] is False

    async def test_verify_unknown_user_fails(self, client):
        login = await client.post("/v1/auth/login", json={"username": "admin", "password": "admin"})
        access = login.json()["access_token"]
        bearer = {"Authorization": f"Bearer {access}"}
        verify = await client.post(
            "/v1/auth/totp/verify",
            json={"username": "ghost-user", "code": "123456"},
            headers=bearer,
        )
        assert verify.json() == {"verified": False, "enabled": False}


class TestInvestigationsBatching:
    async def _seed(self, redis, count):
        for i in range(count):
            await redis.set(
                f"investigation:INV{i:04d}",
                json.dumps({
                    "report": {
                        "txn_id": f"INV{i:04d}",
                        "narrative": "synthetic",
                        "fraud_type": "IMPERSONATION" if i % 2 else "PHISHING",
                        "confidence": "HIGH",
                        "recommended_action": "BLOCK",
                        "key_evidence": [],
                        "reasoning": "test",
                        "generated_at": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
                    }
                }),
            )

    async def test_list_uses_batching_and_pagination(self, client):
        redis = app.state.resources["redis"]
        await self._seed(redis, 25)
        start = time.perf_counter()
        resp = await client.get(
            "/v1/investigations?page=2&page_size=10",
            headers={"X-API-Key": DEV_KEY},
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 25
        assert len(data["results"]) == 10
        assert data["page"] == 2
        assert elapsed_ms < 50, f"listing took {elapsed_ms:.1f}ms"

    async def test_list_filters(self, client):
        redis = app.state.resources["redis"]
        await self._seed(redis, 6)
        resp = await client.get(
            "/v1/investigations?fraud_type=IMPERSONATION",
            headers={"X-API-Key": DEV_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert all(r["fraud_type"] == "IMPERSONATION" for r in data["results"])

    async def test_empty_list(self, client):
        resp = await client.get("/v1/investigations", headers={"X-API-Key": DEV_KEY})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestGraphPagination:
    async def _seed_graph(self, client):
        db = app.state.resources["graph_db"]
        db.create_entity("ROOT", "user", {"risk": 0.9})
        for i in range(10):
            nid = f"NB{i:02d}"
            db.create_entity(nid, "merchant", {"risk": 0.1 * i})
            db.link_entities("ROOT", nid, "transaction", {"amount": 100.0})

    async def test_network_paginated(self, client):
        await self._seed_graph(client)
        resp = await client.get(
            "/v1/graph/network/ROOT?limit=3&offset=0",
            headers={"X-API-Key": DEV_KEY},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_nodes"] == 11
        assert len(data["nodes"]) == 3
        assert data["has_more"] is True

        resp2 = await client.get(
            "/v1/graph/network/ROOT?limit=3&offset=3",
            headers={"X-API-Key": DEV_KEY},
        )
        data2 = resp2.json()
        assert len(data2["nodes"]) == 3
        assert data2["nodes"][0]["id"] != data["nodes"][0]["id"]

    async def test_network_last_page_has_no_more(self, client):
        await self._seed_graph(client)
        resp = await client.get(
            "/v1/graph/network/ROOT?limit=1000&offset=0",
            headers={"X-API-Key": DEV_KEY},
        )
        data = resp.json()
        assert data["has_more"] is False
        assert len(data["nodes"]) == 11


class TestReturnRiskExperiments:
    async def test_experiment_endpoints_require_admin(self, client):
        resp = await client.post(
            "/admin/experiments/return-risk",
            json={
                "champion_weights": {"user_return_rate_30d": 0.25},
                "challenger_weights": {"user_return_rate_30d": 0.30},
            },
            headers={"X-API-Key": "payshield-dev-key-2026"},
        )
        assert resp.status_code in (403, 401)

    async def test_admin_can_create_and_evaluate(self, client):
        from api.auth import auth_manager

        auth_manager.register_api_key("psk-rr-ab-admin", role="admin", name="rr-ab")
        body = {
            "champion_weights": {"user_return_rate_30d": 0.25},
            "challenger_weights": {"user_return_rate_30d": 0.30},
            "traffic_split": 0.1,
        }
        created = await client.post(
            "/admin/experiments/return-risk", json=body, headers={"X-API-Key": "psk-rr-ab-admin"}
        )
        assert created.status_code == 200
        exp_id = created.json()["experiment_id"]

        evaluated = await client.post(
            f"/admin/experiments/return-risk/{exp_id}/evaluate",
            json={"champion": [1, 0, 0, 0, 0], "challenger": [1, 1, 1, 1, 0]},
            headers={"X-API-Key": "psk-rr-ab-admin"},
        )
        assert evaluated.status_code == 200
        data = evaluated.json()
        assert data["recommendation"] == "promote"
        assert data["improvement"] == 0.6
