# ruff: noqa: ARG002 -- test doubles mirror the client interface

# ruff: noqa: ARG001, ARG002, ARG005 -- test doubles mirror the client interface

import asyncio

import pytest


class FakeCtx:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, json=None, timeout=None):
        return FakeCtx(self._responses.pop(0))

    def get(self, url, timeout=None):
        return FakeCtx(self._responses.pop(0))


class JsonDict(dict):
    def __await__(self):
        async def _finish():
            return self

        return _finish().__await__()


class JsonStr(str):
    def __await__(self):
        async def _finish():
            return self

        return _finish().__await__()

    def __call__(self):
        return self


class FakeResp:
    def __init__(self, status=200, payload=None, text="", exc=None):
        self.status = status
        self.status_code = status
        self._payload = payload or {}
        self.text = JsonStr(text)
        self.exc = exc

    def json(self):
        return JsonDict(self._payload)


class MinimalConfig:
    base_url = "http://ollama:11434"
    model = "llama3.1:8b"
    max_tokens = 128
    temperature = 0.1
    timeout = 5
    max_retries = 1
    base_delay = 0.01


@pytest.fixture(autouse=True)
def _patch_retries(monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda *a, **k: real_sleep(0))
    import time as time_module

    monkeypatch.setattr(time_module, "sleep", lambda *a, **k: None)


class TestOllamaClientAsync:
    def _client(self, monkeypatch, responses):
        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        fake = FakeSession(responses)
        monkeypatch.setattr("aiohttp.ClientSession", lambda *a, **k: fake)
        return client

    @pytest.mark.asyncio
    async def test_generate_success(self, monkeypatch):
        client = self._client(monkeypatch, [FakeResp(200, {"response": "BLOCK everything"})])
        out = await client.generate("prompt", max_tokens=64, temperature=0.0)
        assert out == "BLOCK everything"

    @pytest.mark.asyncio
    async def test_generate_retries_then_fallback(self, monkeypatch):
        client = self._client(
            monkeypatch,
            [FakeResp(500, text="boom"), FakeResp(500, text="boom")],
        )
        out = await client.generate("prompt")
        assert out == "LLM investigation unavailable"

    @pytest.mark.asyncio
    async def test_generate_success_after_retry(self, monkeypatch):
        client = self._client(
            monkeypatch,
            [FakeResp(503, text="busy"), FakeResp(200, {"response": "REVIEW"})],
        )
        out = await client.generate("prompt")
        assert out == "REVIEW"

    @pytest.mark.asyncio
    async def test_generate_connection_error(self, monkeypatch):
        import aiohttp

        class FailingSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def post(self, *a, **k):
                raise aiohttp.ClientConnectionError("refused")

        monkeypatch.setattr("aiohttp.ClientSession", lambda *a, **k: FailingSession())
        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        out = await client.generate("prompt")
        assert out == "LLM investigation unavailable"

    @pytest.mark.asyncio
    async def test_health_model_found(self, monkeypatch):
        client = self._client(
            monkeypatch,
            [FakeResp(200, {"models": [{"name": "llama3.1:8b"}]})],
        )
        assert await client.health() is True

    @pytest.mark.asyncio
    async def test_health_model_missing(self, monkeypatch):
        client = self._client(
            monkeypatch,
            [FakeResp(200, {"models": [{"name": "qwen"}]})],
        )
        assert await client.health() is False

    @pytest.mark.asyncio
    async def test_health_non_200(self, monkeypatch):
        client = self._client(monkeypatch, [FakeResp(500)])
        assert await client.health() is False

    @pytest.mark.asyncio
    async def test_pull_model_success(self, monkeypatch):
        client = self._client(monkeypatch, [FakeResp(200)])
        assert await client.pull_model("llama3.1:8b") is True

    @pytest.mark.asyncio
    async def test_pull_model_failure(self, monkeypatch):
        client = self._client(monkeypatch, [FakeResp(400, text="missing")])
        assert await client.pull_model("nope") is False


class TestOllamaClientSync:
    def _client(self, monkeypatch, fake_post):
        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        monkeypatch.setattr("requests.post", fake_post)
        return client

    def test_generate_sync_success(self, monkeypatch):
        def fake(*a, **k):
            return FakeResp(200, {"response": "ALLOW"})
        assert self._client(monkeypatch, fake).generate_sync("p") == "ALLOW"

    def test_generate_sync_retries_then_fallback(self, monkeypatch):
        def fake(*a, **k):
            return FakeResp(500, text="err")
        out = self._client(monkeypatch, fake).generate_sync("p")
        assert out == "LLM investigation unavailable"

    def test_generate_sync_request_error(self, monkeypatch):
        import requests

        def fake(*a, **k):
            raise requests.ConnectionError("down")

        out = self._client(monkeypatch, fake).generate_sync("p")
        assert out == "LLM investigation unavailable"

    def test_health_sync_found(self, monkeypatch):
        def fake(*a, **k):
            return FakeResp(200, {"models": [{"name": "llama3.1:8b"}]})
        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        monkeypatch.setattr("requests.get", fake)
        assert client.health_sync() is True

    def test_health_sync_missing(self, monkeypatch):
        def fake(*a, **k):
            return FakeResp(200, {"models": [{"name": "other"}]})
        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        monkeypatch.setattr("requests.get", fake)
        assert client.health_sync() is False

    def test_health_sync_request_error(self, monkeypatch):
        import requests

        def fake(*a, **k):
            raise requests.ConnectionError("down")

        from llm.client import OllamaClient

        client = OllamaClient(MinimalConfig())
        monkeypatch.setattr("requests.get", fake)
        assert client.health_sync() is False


class TestLLMInvestigator:
    @pytest.fixture(autouse=True)
    def _client(self, monkeypatch):
        import llm.investigator as investigator_module

        calls = []

        class FakeOllamaClient:
            def generate(self, model=None, prompt=None, options=None):
                calls.append((model, prompt, options))
                return {"response": "User is part of a mule ring with rapid cycling transfers"}

        monkeypatch.setattr(
            investigator_module.ollama, "Client", lambda host=None: FakeOllamaClient()
        )
        monkeypatch.setattr(investigator_module.os, "getenv", lambda k, d="": d)
        self.calls = calls

    def test_investigate_parses_mule_ring(self):
        from llm.investigator import LLMInvestigator

        investigator = LLMInvestigator(base_url="http://localhost:11434")
        result = investigator.investigate(
            {
                "layer1_rules": ["V-RULE-01", "V-RULE-03"],
                "gnn_explanation": {
                    "fraud_probability": 0.9,
                    "evidence_subgraph": ["A -> B", "B -> C"],
                },
                "layer1_chi2": 12.34,
            }
        )
        assert result["fraud_type"] == "MULE_RING"
        assert result["recommended_action"].startswith("Block")
        assert self.calls[0][0] == "llama3.1:8b"
        prompt = self.calls[0][1]
        assert "V-RULE-01" in prompt
        assert "0.900" in prompt

    def test_build_alerts_various_sources(self):
        from llm.investigator import LLMInvestigator

        investigator = LLMInvestigator(base_url="http://localhost:11434")
        alerts = investigator._build_alerts(
            {
                "layer1_rules": ["R1"],
                "gnn_explanation": {
                    "fraud_probability": 0.6,
                    "evidence_subgraph": ["X -> Y"],
                },
                "layer1_chi2": 4.5,
            }
        )
        assert len(alerts) == 4

    def test_parse_narrative_classifications(self):
        from llm.investigator import LLMInvestigator

        investigator = LLMInvestigator(base_url="http://localhost:11434")
        assert (
            investigator._parse_narrative("burst of rapid velocity transfers", {})[
                "fraud_type"
            ]
            == "BURST_ATTACK"
        )
        assert (
            investigator._parse_narrative("merchant collusion with shell entities", {})[
                "fraud_type"
            ]
            == "MERCHANT_COLLUSION"
        )
        assert (
            investigator._parse_narrative("account takeover via login geo anomaly", {})[
                "fraud_type"
            ]
            == "ATO"
        )
        assert (
            investigator._parse_narrative("nothing suspicious here", {})["fraud_type"]
            == "OTHER"
        )
        assert (
            investigator._parse_narrative("", {})["narrative"] == "No narrative generated"
        )

    def test_action_thresholds(self):
        from llm.investigator import LLMInvestigator

        investigator = LLMInvestigator(base_url="http://localhost:11434")
        high = investigator._parse_narrative(
            "x", {"gnn_explanation": {"fraud_probability": 0.95}}
        )
        assert "Block" in high["recommended_action"]
        mid = investigator._parse_narrative(
            "x", {"gnn_explanation": {"fraud_probability": 0.6}}
        )
        assert "manual review" in mid["recommended_action"]
        low = investigator._parse_narrative(
            "x", {"gnn_explanation": {"fraud_probability": 0.1}}
        )
        assert "No action" in low["recommended_action"]
        assert low["confidence"] == 0.5
