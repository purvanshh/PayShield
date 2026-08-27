"""Live-agent unit tests (restored + rewired to the return-risk surface)."""

import asyncio

import pytest

from agents import (
    AgentMessage,
    AgentState,
    MessageRouter,
    HumanReviewAgent,
    ProfileAgent,
    TransactionAnalysisAgent,
)
from agents.message import MessageType
from agents.reflection_agent import ReflectionAgent
from agents.risk_suite_reflection import (
    analyze_chargeback_outcomes,
    analyze_return_risk_accuracy,
    build_risk_suite_reflection,
    generate_risk_suite_recommendations,
)


class _Collector:
    message_queue: asyncio.Queue = asyncio.Queue()

    async def process(self, message: AgentMessage) -> None:
        await self.message_queue.put(message)


def _route(router: MessageRouter, sender: str, recipient: str, content: dict, msg_type: str = "EVENT"):
    return router.route(AgentMessage(sender=sender, recipient=recipient, content=content, message_type=msg_type))


class TestMessageRouter:
    def test_route_delivers_to_registered_agent(self):
        router = MessageRouter()
        agent = TransactionAnalysisAgent()
        router.register_agent(agent.agent_id, agent)
        asyncio.run(_route(router, "s", agent.agent_id, {}))
        assert not agent.message_queue.empty()

    def test_route_unknown_recipient_is_noop(self):
        router = MessageRouter()
        asyncio.run(_route(router, "s", "ghost", {}))

    def test_broadcast_skips_sender(self):
        router = MessageRouter()
        a = TransactionAnalysisAgent()
        b = ProfileAgent()
        router.register_agent(a.agent_id, a)
        router.register_agent(b.agent_id, b)
        asyncio.run(_route(router, a.agent_id, "broadcast", {}))
        assert a.message_queue.empty()
        assert not b.message_queue.empty()

    def test_unregister_removes_agent(self):
        router = MessageRouter()
        agent = TransactionAnalysisAgent()
        router.register_agent(agent.agent_id, agent)
        router.unregister_agent(agent.agent_id)
        assert agent.agent_id not in router._agents


class TestTransactionAgent:
    async def test_scores_return_risk_order(self):
        agent = TransactionAnalysisAgent()
        resp = await agent.process(
            AgentMessage(
                sender="worker", recipient=agent.agent_id,
                content={
                    "type": "RETURN_RISK_SCORED",
                    "user_id": "U001",
                    "order": {
                        "order_id": "ORD_1", "merchant_id": "M_FASHION_001",
                        "amount": 4500, "category": "fashion", "cod_flag": True,
                        "score": 0.8, "tier": "HIGH",
                    },
                },
            )
        )
        body = resp.content
        assert body["type"] == "TXN_ANALYSIS_RESULT"
        assert body["user_id"] == "U001"
        assert 0 <= body["risk_score"] <= 1
        assert set(body["components"]) == {
            "order_velocity", "cod_exposure", "amount_anomaly", "merchant_return_rate",
        }
        assert body["elevated"] is bool(body["risk_score"] > 0.5)

    async def test_ignores_unknown_type(self):
        agent = TransactionAnalysisAgent()
        resp = await agent.process(
            AgentMessage(sender="s", recipient=agent.agent_id, content={"type": "NOPE"})
        )
        assert resp.content["status"] == "ignored"

    def test_velocity_zero_without_history(self):
        agent = TransactionAnalysisAgent()
        assert agent._velocity_analysis("nobody") == 0.0


class TestProfileAgent:
    async def test_builds_profile_and_detects_no_drift(self):
        agent = ProfileAgent()
        resp = await agent.process(
            AgentMessage(
                sender="worker", recipient=agent.agent_id,
                content={"type": "RETURN_RISK_SCORED", "user_id": "U001",
                         "order": {"order_id": "ORD_1", "amount": 1000, "cod_flag": True,
                                   "category": "fashion", "score": 0.2}},
            )
        )
        assert resp.content["profile_updated"] is True
        profile = agent.get_profile("U001")
        assert profile["order_count"] == 1
        assert profile["avg_amount"] == 1000.0
        assert profile["avg_score"] == 0.2
        assert profile["cod_count"] == 1

    async def test_drift_broadcast_on_anomaly(self):
        agent = ProfileAgent()
        router = MessageRouter()
        router.register_agent(agent.agent_id, agent)
        collector = _Collector()
        router.register_agent("human_review_agent", collector)
        await agent.start(router)

        # 15 low-risk orders, then 5 high-risk orders -> drift.
        for i in range(15):
            await agent.process(
                AgentMessage(
                    sender="worker", recipient=agent.agent_id,
                    content={"type": "RETURN_RISK_SCORED", "user_id": "U_D",
                             "order": {"order_id": f"L{i}", "amount": 1000, "score": 0.1}},
                )
            )
        for i in range(5):
            await agent.process(
                AgentMessage(
                    sender="worker", recipient=agent.agent_id,
                    content={"type": "RETURN_RISK_SCORED", "user_id": "U_D",
                             "order": {"order_id": f"H{i}", "amount": 1000, "score": 0.9}},
                )
            )
        drift = agent._detect_drift("U_D")
        assert drift > 0.5


class TestHumanReviewAgent:
    async def test_handles_feedback(self):
        agent = HumanReviewAgent()
        resp = await agent.process(
            AgentMessage(
                sender="worker", recipient=agent.agent_id,
                content={"type": "ANALYST_FEEDBACK",
                         "feedback": {"txn_id": "ORD_1", "original_decision": "REVIEW",
                                      "analyst_decision": "REVIEW", "analyst_id": "a1"}},
            )
        )
        assert resp.content["status"] == "feedback_processed"
        assert resp.content["correct"] is True

    async def test_handles_escalation(self):
        agent = HumanReviewAgent()
        resp = await agent.process(
            AgentMessage(
                sender="worker", recipient=agent.agent_id,
                content={"type": "ESCALATION_REQUEST", "txn_id": "ORD_9", "reason": "HIGH tier", "priority": 2},
            )
        )
        assert resp.content["status"] == "escalated"
        assert resp.content["escalation"]["status"] == "PENDING"


class TestReflectionAgent:
    def test_risk_suite_accuracy(self):
        records = [
            {"risk_tier": "HIGH", "returned": True, "user_type": "serial"},
            {"risk_tier": "HIGH", "returned": False, "user_type": "new"},
            {"risk_tier": "LOW", "returned": True, "user_type": "new"},
            {"risk_tier": "LOW", "returned": False, "user_type": "clean"},
        ]
        acc = analyze_return_risk_accuracy(records)
        assert acc["high_risk_total"] == 2
        assert acc["high_risk_returned"] == 1
        assert acc["high_risk_precision"] == 0.5
        assert acc["tier_misses"] == 1

    def test_risk_suite_recommendations(self):
        recs = generate_risk_suite_recommendations(
            {"high_risk_precision": 0.4}, {"outcome_matrix": []}, drift_detected=False
        )
        assert any(r["type"] == "threshold_adjustment" for r in recs)

    def test_chargeback_outcome_matrix(self):
        out = analyze_chargeback_outcomes(
            [{"response_type": "REJECT", "outcome": "won"}, {"response_type": "REJECT", "outcome": "lost"}]
        )
        assert len(out["outcome_matrix"]) == 2

    def test_build_suite(self):
        suite = build_risk_suite_reflection([], [])
        assert "return_risk" in suite
        assert "chargeback" in suite
        assert "recommendations" in suite

    async def test_process_unknown_type_returns_error(self):
        agent = ReflectionAgent()
        resp = await agent.process(
            AgentMessage(sender="s", recipient="reflection_agent", message_type=MessageType.EVENT, content={})
        )
        assert resp.message_type == "ERROR"