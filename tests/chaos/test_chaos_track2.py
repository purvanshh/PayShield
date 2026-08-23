# ruff: noqa: ARG001, ARG002 -- doubles mirror the OllamaClient/redis interfaces

"""Chaos experiments for the Track 2 components (Phase 35).

Three infrastructure-failure modes, each with a documented graceful
behaviour:

1. Redis outage during return-risk scoring  -> neutral defaults with
   ``default_redis_error`` provenance tags; the score degrades, the API
   survives (no retry loop, no exception).
2. LLM outage during chargeback narrative   -> deterministic fallback
   narrative; the rebuttal is still generated.
3. Razorpay submit timeout                  -> RazorpayAPIError(503)
   surfaced immediately; no silent hang, no duplicate submission
   possible (submit is the only POST path and it is idempotent-safe).

All three are deterministic and hermetic.
"""

from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from chargeback.exceptions import RazorpayAPIError
from chargeback.narrative_generator import NarrativeGenerator
from chargeback.razorpay_client import RazorpayClient
from return_risk.feature_engine import ReturnRiskFeatureEngine
from return_risk.rules_engine import RulesEngine
from return_risk.scorer import ReturnRiskScorer
from tests.fake_redis import FakeRedis


class BrokenRedis:
    """A Redis double whose every call raises (simulating an outage)."""

    async def hgetall(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def zrangebyscore(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def zscore(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def zadd(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def hincrby(self, *args, **kwargs):
        raise ConnectionError("Redis down")

    async def hmset(self, *args, **kwargs):
        raise ConnectionError("Redis down")


def _bundle():
    from api.schemas.chargeback import EvidenceBundle, TransactionProof

    return EvidenceBundle(
        transaction_proof=TransactionProof(
            txn_timestamp=datetime(2026, 7, 20), amount=Decimal("4500"), merchant_id="M001"
        ),
        completeness_score=0.9,
    )


class FakeCollector:
    def __init__(self, bundle):
        self.bundle = bundle

    async def collect_evidence(self, transaction_id, dispute_id=""):
        self.bundle.audit_trail = []
        return self.bundle


class TestRedisOutageReturnRisk:
    async def test_scoring_degrades_to_neutral_defaults(self):
        engine = ReturnRiskFeatureEngine(BrokenRedis())
        scorer = ReturnRiskScorer(feature_engine=engine, rules_engine=RulesEngine())

        result = await scorer.score(
            user_id="U_ANY",
            merchant_id="M_ANY",
            order_id="ORD_CHAOS_1",
            amount=Decimal("3000"),
            category="fashion",
            cod_flag=False,
            timestamp=datetime(2026, 8, 21, 10, 0),
        )

        # no crash, score in range, and the degradation is visible
        assert 0 <= result["return_risk_score"] <= 1
        assert result["user_profile"]["is_new_user"] is True
        assert (
            result["feature_breakdown"]["user_return_rate_30d"]["source"] == "default_redis_error"
        )
        assert (
            result["feature_breakdown"]["merchant_return_rate_30d"]["source"]
            == "default_redis_error"
        )

    async def test_rules_still_evaluate_on_defaults(self):
        engine = ReturnRiskFeatureEngine(BrokenRedis())
        scorer = ReturnRiskScorer(feature_engine=engine, rules_engine=RulesEngine())
        result = await scorer.score(
            user_id="U_ANY",
            merchant_id="M_ANY",
            order_id="ORD_CHAOS_2",
            amount=Decimal("3000"),
            category="fashion",
            cod_flag=False,
            timestamp=datetime(2026, 8, 21, 10, 0),
        )
        # no rules should fire for a completely flat profile
        assert [r["rule_id"] for r in result["rules_triggered"] if r["triggered"]] == []


class TestLLMOutageChargeback:
    async def test_rebuttal_survives_llm_timeout(self, tmp_path):
        from store.audit_log import AuditLogWriter

        writer = AuditLogWriter(str(tmp_path))
        writer.append(
            "SCORE_DECISION",
            "U001",
            "ALLOW",
            {"txn_id": "TXN_CHAOS_1", "merchant_id": "M001", "amount": 4500.0,
             "device_fingerprint": "DEV-1", "triggered_rules": []},
        )

        class TimeoutLLM:
            async def generate(self, prompt, max_tokens=None, temperature=None):
                raise TimeoutError("Ollama timeout")

        from chargeback.evidence_collector import ChargebackEvidenceCollector
        from chargeback.rebuttal_builder import ChargebackRebuttalBuilder
        from store.audit_log import AuditLogReader

        collector = ChargebackEvidenceCollector(redis=FakeRedis(), audit_reader=AuditLogReader(str(tmp_path)))
        builder = ChargebackRebuttalBuilder(
            evidence_collector=collector,
            llm_client=TimeoutLLM(),
            razorpay_client=RazorpayClient(mock_mode=True),
            config={"confidence_threshold": 0.6},
        )
        rebuttal = await builder.build_rebuttal(
            dispute_id="CB_CHAOS_1",
            payment_id="pay_CHAOS_1",
            transaction_id="TXN_CHAOS_1",
            network="VISA",
            reason_code="10.4",
        )

        assert rebuttal.narrative is not None
        assert rebuttal.narrative.summary
        assert rebuttal.narrative.quality_score == 0.5  # deterministic fallback
        assert rebuttal.response_type in ("ACCEPT", "REJECT", "PARTIAL")

    async def test_narrative_generator_fallback_chain(self):
        class BrokenLLM:
            async def generate(self, prompt, max_tokens=None, temperature=None):
                raise TimeoutError("down")

        generator = NarrativeGenerator(llm_client=BrokenLLM())
        narrative = await generator.generate(_bundle(), "10.4", "fraud", "REJECT")
        assert narrative.summary and narrative.quality_score == 0.5


class TestRazorpayTimeout:
    async def test_submission_timeout_surfaces_as_503_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Request timeout", request=request)

        client = RazorpayClient(
            api_key="k", api_secret="s", transport=httpx.MockTransport(handler), timeout=1.0
        )
        with pytest.raises(RazorpayAPIError) as exc_info:
            await client.submit_contest("CB_001", {"contest": True, "evidence": {}})
        assert exc_info.value.status_code == 503
        assert "timeout" in str(exc_info.value).lower() or "unreachable" in str(exc_info.value).lower()
        await client.close()

    async def test_contested_timeout_via_document_path(self):
        from api.schemas.chargeback import ChargebackRebuttalDocument

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("connect timeout", request=request)

        client = RazorpayClient(
            api_key="k", api_secret="s", transport=httpx.MockTransport(handler), timeout=1.0
        )
        rebuttal = ChargebackRebuttalDocument(
            dispute_id="CB_002",
            payment_id="pay_002",
            transaction_id="TXN_002",
            reason_code="10.4",
            response_type="REJECT",
            response_deadline="2026-09-20T00:00:00Z",
            razorpay_payload={"contest": True},
        )
        with pytest.raises(RazorpayAPIError):
            await client.contest_chargeback("CB_002", rebuttal)
        await client.close()


class TestLLMTimeoutCap:
    async def test_slow_llm_is_capped_and_falls_back(self):
        """A stalled LLM must never hold the rebuttal path hostage."""
        import asyncio
        import time

        from chargeback.narrative_generator import NarrativeGenerator

        class SleepyLLM:
            async def generate(self, prompt, max_tokens=None, temperature=None):
                await asyncio.sleep(30)  # would block 30s without the guard

        generator = NarrativeGenerator(llm_client=SleepyLLM(), llm_timeout=0.2)
        start = time.perf_counter()
        narrative = await generator.generate(_bundle(), "10.4", "fraud", "REJECT")
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0
        assert narrative.quality_score == 0.5
        assert narrative.summary
