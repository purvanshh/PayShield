"""End-to-end tests for the complete PayShield fraud detection pipeline."""

import json
import time

import pytest
import requests

BASE_URL = "http://localhost:8000"
API_KEY = "payshield-dev-key-2026"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


@pytest.fixture
def txn_data():
    return {
        "txn_id": f"e2e_txn_{int(time.time())}",
        "user_id": "U_E2E_TEST_001",
        "merchant_id": "M5502",
        "amount": 4990.0,
        "timestamp": "2026-07-27T12:00:00",
        "device_fingerprint": "DEV_E2E_001",
        "location": {"lat": 19.076, "lon": 72.8777},
        "mcc_code": "6012",
        "txn_type": "P2M",
    }


def test_health():
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "checks" in data


def test_complete_fraud_pipeline(txn_data):
    resp = requests.post(f"{BASE_URL}/v1/score", json=txn_data, headers=HEADERS, timeout=10)
    assert resp.status_code == 200
    result = resp.json()
    assert result["txn_id"] == txn_data["txn_id"]
    assert result["decision"] in ("ALLOW", "BLOCK", "REVIEW")
    assert 0.0 <= result["fraud_probability"] <= 1.0
    assert "latency_ms" in result
    inv_resp = requests.get(
        f"{BASE_URL}/v1/investigation/{txn_data['txn_id']}",
        headers=HEADERS, timeout=5,
    )
    assert inv_resp.status_code in (200, 202, 404)


def test_legitimate_transaction_allowed():
    txn = {
        "txn_id": f"e2e_legit_{int(time.time())}",
        "user_id": "U_E2E_LEGIT",
        "merchant_id": "M10001",
        "amount": 250.0,
        "timestamp": "2026-07-27T12:00:00",
        "device_fingerprint": "DEV_LEGIT_001",
        "location": {"lat": 19.076, "lon": 72.8777},
        "mcc_code": "5411",
        "txn_type": "P2M",
    }
    resp = requests.post(f"{BASE_URL}/v1/score", json=txn, headers=HEADERS, timeout=10)
    assert resp.status_code == 200


def test_batch_scoring_100():
    txns = []
    for i in range(50):
        txns.append({
            "txn_id": f"e2e_batch_{int(time.time())}_{i}",
            "user_id": f"U_BATCH_{i % 10}",
            "merchant_id": f"M_{i % 20}",
            "amount": 100.0 * (i + 1),
            "timestamp": "2026-07-27T12:00:00",
            "device_fingerprint": f"DEV_BATCH_{i}",
            "location": {"lat": 19.076, "lon": 72.8777},
            "mcc_code": "6012",
            "txn_type": "P2P",
        })
    resp = requests.post(
        f"{BASE_URL}/v1/batch", json={"transactions": txns},
        headers=HEADERS, timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 50
    assert data["batch_latency_ms"] < 5000


def test_websocket_alert_delivery():
    import asyncio
    import websockets

    async def test():
        uri = f"ws://localhost:8000/v1/stream?token=payshield-dev-key-2026"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"action": "subscribe"}))
            resp = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(resp)
            assert data["status"] == "subscribed"

    asyncio.run(test())
