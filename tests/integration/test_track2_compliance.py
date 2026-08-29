"""Track 2 compliance meta-endpoint tests."""

import pytest
from httpx import ASGITransport, AsyncClient

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


class TestTrack2Compliance:
    async def test_requires_auth(self, client):
        resp = await client.get("/v1/meta/track2-compliance")
        assert resp.status_code == 403

    async def test_returns_requirement_map(self, client):
        resp = await client.get(
            "/v1/meta/track2-compliance", headers={"X-API-Key": DEV_KEY}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall"]
        assert isinstance(data["requirements"], list)
        assert len(data["requirements"]) >= 14

    async def test_every_item_is_well_formed(self, client):
        resp = await client.get(
            "/v1/meta/track2-compliance", headers={"X-API-Key": DEV_KEY}
        )
        data = resp.json()
        for item in data["requirements"]:
            assert item["name"]
            assert item["status"] in ("done", "planned")
            assert item["implementation"]
            assert item["evidence"]

    async def test_core_surfaces_are_done_and_planned_are_flagged(self, client):
        resp = await client.get(
            "/v1/meta/track2-compliance", headers={"X-API-Key": DEV_KEY}
        )
        data = resp.json()
        statuses = {item["name"]: item["status"] for item in data["requirements"]}
        # Core surfaces that must already be implemented and verified.
        for core in (
            "Return-Risk Scorer (pre-ship tier)",
            "Fraud-Spike Detector (velocity / geo / device)",
            "Chargeback Evidence Responder",
            "Signed Razorpay Webhooks (HMAC, 400 on bad signature)",
            "Live-Stack Verification (11/11)",
        ):
            assert statuses.get(core) == "done", f"{core!r} must be marked done"
        # Planned items must not be misrepresented as done.
        for planned in (
            "Abuse-Ring Sentinel (shared address-hash velocity)",
            "Guided Demo Mode (10-minute tour)",
            "Feature-Waterfall Explainability (XAI)",
        ):
            assert statuses.get(planned) == "planned", f"{planned!r} must be planned"
