import asyncio

import pytest

from agents import (
    AgentMessage,
    AgentState,
    MessagePriority,
    MessageRouter,
    MessageType,
    ProfileAgent,
    TransactionAnalysisAgent,
)
from agents.archived import (
    CollectiveIntelligenceAgent,
    CriticAgent,
    MitigationAgent,
    PlannerAgent,
)
from agents.archived.collective_agent import AgentAccuracyTracker
from agents.message import AgentMessage as MessageCls


class TestMessageRouter:
    def test_route_delivers_to_registered_agent(self):
        router = MessageRouter()
        agent = TransactionAnalysisAgent()
        router.register_agent(agent.agent_id, agent)
        message = AgentMessage(sender="s", recipient=agent.agent_id, content={})
        asyncio.run(router.route(message))
        assert not agent.message_queue.empty()

    def test_route_unknown_recipient_is_noop(self):
        router = MessageRouter()
        message = AgentMessage(sender="s", recipient="ghost", content={})
        asyncio.run(router.route(message))

    def test_broadcast_skips_sender(self):
        router = MessageRouter()
        a = TransactionAnalysisAgent()
        b = CriticAgent()
        router.register_agent(a.agent_id, a)
        router.register_agent(b.agent_id, b)
        message = AgentMessage(sender=a.agent_id, recipient="broadcast", content={})
        asyncio.run(router.route(message))
        assert a.message_queue.empty()
        assert not b.message_queue.empty()

    def test_unregister_removes_agent(self):
        router = MessageRouter()
        agent = TransactionAnalysisAgent()
        router.register_agent(agent.agent_id, agent)
        router.unregister_agent(agent.agent_id)
        assert agent.agent_id not in router._agents


class TestAgentMessage:
    def test_roundtrip(self):
        msg = AgentMessage(
            sender="a",
            recipient="b",
            message_type="REQUEST",
            content={"k": "v"},
            priority=MessagePriority.HIGHEST,
        )
        restored = MessageCls.from_dict(msg.to_dict())
        assert restored.sender == "a"
        assert restored.recipient == "b"
        assert restored.content == {"k": "v"}
        assert restored.priority == 1


class TestBaseAgentLifecycle:
    def test_start_stop_state_transitions(self):
        agent = ProfileAgent()
        router = MessageRouter()
        asyncio.run(agent.start(router))
        assert agent._running is True
        asyncio.run(agent.stop())
        assert agent.state == AgentState.TERMINATED

    def test_send_message_without_router_warns(self):
        agent = CriticAgent()
        asyncio.run(agent.send_message("other", {"k": "v"}))

    def test_run_loop_returns_when_not_running(self):
        agent = ProfileAgent()
        asyncio.run(agent.run())
        assert agent.state == AgentState.IDLE


class TestTransactionAnalysisAgent:
    def test_score_request_returns_risk_score(self):
        agent = TransactionAnalysisAgent()
        message = AgentMessage(
            sender="harness",
            recipient=agent.agent_id,
            message_type="REQUEST",
            content={
                "type": "TXN_SCORE_REQUEST",
                "txn": {
                    "user_id": "U_TEST",
                    "merchant_id": "M5502",
                    "amount": 4990.0,
                    "device_id": "D1",
                    "location": "Mumbai",
                },
            },
        )
        response = asyncio.run(agent.process(message))
        assert response.recipient == "harness"
        assert 0.0 <= response.content.get("risk_score", -1) <= 1.0
        assert "components" in response.content

    def test_unknown_type_ignored(self):
        agent = TransactionAnalysisAgent()
        message = AgentMessage(
            sender="harness",
            recipient=agent.agent_id,
            content={"type": "NOPE"},
        )
        response = asyncio.run(agent.process(message))
        assert response.content["status"] == "ignored"


class TestPlannerAgent:
    def test_decompose_investigation_builds_plan(self):
        planner = PlannerAgent()
        plan = planner.decompose_investigation(
            {
                "transaction_id": "T1",
                "amount": 1000.0,
                "user": {"id": "U1"},
                "device": {"fingerprint": "D1"},
                "merchant": {"id": "M5502"},
            },
            confidence=0.85,
        )
        assert plan.transaction_id == "T1"
        assert len(plan.strategies) == 3
        plan.select_best_strategy()
        assert plan.selected_strategy is not None
        assert plan.sub_tasks

    def test_process_plan_request(self):
        planner = PlannerAgent()
        message = AgentMessage(
            sender="s",
            recipient=planner.agent_id,
            message_type=MessageType.COMPLEX_INVESTIGATION_REQUEST,
            content={
                "transaction": {"transaction_id": "T1", "user_id": "U1"},
                "confidence": 0.9,
            },
        )
        response = asyncio.run(planner.process(message))
        assert response.message_type == MessageType.INVESTIGATION_PLAN
        assert response.content["transaction_id"] == "T1"

    def test_process_rejects_unexpected_message_type(self):
        planner = PlannerAgent()
        message = AgentMessage(
            sender="s",
            recipient=planner.agent_id,
            message_type=MessageType.REQUEST,
            content={},
        )
        response = asyncio.run(planner.process(message))
        assert response.message_type == "ERROR"


class TestCriticAgent:
    def test_challenges_low_confidence_block(self):
        critic = CriticAgent()
        result = critic.evaluate_decision({"confidence": 0.5, "action": "BLOCK"})
        assert result.should_challenge
        assert any("confidence" in c["reason"] for c in result.challenges)

    def test_confirms_high_confidence_block(self):
        critic = CriticAgent()
        result = critic.evaluate_decision({"confidence": 0.95, "action": "BLOCK"})
        assert not result.should_challenge
        assert result.challenges == []

    def test_challenges_single_agent_dissent(self):
        critic = CriticAgent()
        result = critic.evaluate_decision(
            {"confidence": 0.9, "action": "BLOCK", "single_agent_dissent": True}
        )
        assert result.should_challenge

    def test_accuracy_tracks_outcomes(self):
        critic = CriticAgent()
        critic.record_challenge_outcome(True)
        critic.record_challenge_outcome(True)
        critic.record_challenge_outcome(False)
        assert critic.accuracy == pytest.approx(2 / 3)

    def test_process_challenges_collective_decision(self):
        critic = CriticAgent()
        message = AgentMessage(
            sender="s",
            recipient=critic.agent_id,
            message_type=MessageType.COLLECTIVE_DECISION,
            content={"decision": {"confidence": 0.4, "action": "BLOCK", "transaction_id": "T1"}},
        )
        response = asyncio.run(critic.process(message))
        assert response.message_type == MessageType.DECISION_CHALLENGE


class TestCollectiveIntelligence:
    def test_tracker_precision(self):
        tracker = AgentAccuracyTracker()
        tracker.record_outcome("L1", True)
        tracker.record_outcome("L1", True)
        tracker.record_outcome("L1", False)
        assert tracker.get_precision("L1") == pytest.approx(2 / 3)
        assert tracker.get_precision("UNSEEN") == 0.5
        adjustment = tracker.get_weight_adjustment("L1", base_weight=0.4)
        assert adjustment == pytest.approx(0.4 + (2 / 3 - 0.5) * 0.2, abs=1e-4)
        assert tracker.get_weight_adjustment("L1", base_weight=0.5) <= 0.5

    def test_tracker_caps_history_at_100(self):
        tracker = AgentAccuracyTracker()
        for _ in range(120):
            tracker.record_outcome("L2", True)
        assert len(tracker._accuracy["L2"]) == 100

    def test_assessment_request_returns_fused_signal(self):
        collective = CollectiveIntelligenceAgent()
        message = AgentMessage(
            sender="s",
            recipient=collective.agent_id,
            content={
                "type": "COLLECTIVE_ASSESSMENT_REQUEST",
                "signals": {"L1": 0.8, "L2": 0.6, "LLM": 0.7},
            },
        )
        response = asyncio.run(collective.process(message))
        assert response.recipient == "s"
        assert 0.0 <= response.content["fraud_probability"] <= 1.0
        assert response.content["decision"] in ("BLOCK", "REVIEW", "ALLOW")
        assert "weights" in response.content

    def test_feedback_updates_weights(self):
        collective = CollectiveIntelligenceAgent()
        message = AgentMessage(
            sender="s",
            recipient=collective.agent_id,
            content={"type": "AGENT_FEEDBACK", "agent_type": "L1", "correct": True},
        )
        response = asyncio.run(collective.process(message))
        assert response.content["status"] == "feedback_processed"

    def test_ignored_type(self):
        collective = CollectiveIntelligenceAgent()
        message = AgentMessage(sender="s", recipient=collective.agent_id, content={"type": "NOPE"})
        response = asyncio.run(collective.process(message))
        assert response.content["status"] == "ignored"


class TestMitigationAgent:
    def test_executes_high_confidence_block(self):
        agent = MitigationAgent()
        message = AgentMessage(
            sender="s",
            recipient=agent.agent_id,
            content={"type": "COLLECTIVE_DECISION", "decision": "BLOCK", "fraud_probability": 0.95},
        )
        response = asyncio.run(agent.process(message))
        assert response.content["status"] == "EXECUTED"
        assert response.content["action"] == "BLOCK"

    def test_low_confidence_block_requires_confirmation(self):
        agent = MitigationAgent()
        message = AgentMessage(
            sender="s",
            recipient=agent.agent_id,
            content={"type": "COLLECTIVE_DECISION", "decision": "BLOCK", "fraud_probability": 0.5},
        )
        response = asyncio.run(agent.process(message))
        assert response.content["status"] == "PENDING_CONFIRMATION"

    def test_rollback_requires_admin(self):
        agent = MitigationAgent()
        message = AgentMessage(
            sender="s",
            recipient=agent.agent_id,
            content={"type": "ROLLBACK_REQUEST", "action_id": "act_1"},
        )
        response = asyncio.run(agent.process(message))
        assert response.content["status"] == "rejected"

    def test_ignored_type(self):
        agent = MitigationAgent()
        message = AgentMessage(
            sender="s",
            recipient=agent.agent_id,
            content={"type": "NOPE", "decision": "BLOCK"},
        )
        response = asyncio.run(agent.process(message))
        assert response.content["status"] == "ignored"
