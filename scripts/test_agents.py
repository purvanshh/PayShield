import argparse
import asyncio
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import AgentConfig, AgentMessage, MessageRouter, ProfileAgent, TransactionAnalysisAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Test agent interactions")
    parser.add_argument("--user-id", default="U_TEST_001")
    parser.add_argument("--merchant-id", default="M5502")
    parser.add_argument("--amount", type=float, default=4990.0)
    args = parser.parse_args()

    router = MessageRouter()
    profile = ProfileAgent()
    txn_agent = TransactionAnalysisAgent()

    await profile.start(router)
    await txn_agent.start(router)
    router.register_agent(profile.agent_id, profile)
    router.register_agent(txn_agent.agent_id, txn_agent)

    txn = {
        "user_id": args.user_id,
        "merchant_id": args.merchant_id,
        "amount": args.amount,
        "device_id": "D8841",
        "location": "Mumbai",
    }

    print(f"\n{'=' * 60}")
    print("AGENT INTERACTION TEST")
    print(f"{'=' * 60}")
    print(f"User: {args.user_id}, Merchant: {args.merchant_id}, Amount: {args.amount}")

    txn_msg = AgentMessage(
        sender="test_harness",
        recipient=txn_agent.agent_id,
        message_type="REQUEST",
        content={"type": "TXN_SCORE_REQUEST", "txn": txn},
        priority=1,
    )
    response = await txn_agent.process(txn_msg)
    risk = response.content.get("risk_score", 0)
    components = response.content.get("components", {})
    print(f"\nTransaction Analysis Risk Score: {risk:.4f}")
    for k, v in components.items():
        print(f"  {k}: {v:.4f}")

    profile_msg = AgentMessage(
        sender="test_harness",
        recipient=profile.agent_id,
        message_type="REQUEST",
        content={"type": "USER_TXN_EVENT", "user_id": args.user_id, "txn": txn},
    )
    pr_response = await profile.process(profile_msg)
    drift = pr_response.content.get("drift_score", 0)
    anomaly = pr_response.content.get("anomaly", False)
    print(f"\nProfile Drift Score: {drift:.4f}")
    print(f"Anomaly Flagged: {anomaly}")

    for i in range(5):
        sim_txn = {**txn, "amount": 4500 + i * 100}
        await profile.process(AgentMessage(
            sender="test", recipient=profile.agent_id,
            message_type="EVENT",
            content={"type": "USER_TXN_EVENT", "user_id": args.user_id, "txn": sim_txn},
        ))
        await txn_agent.process(AgentMessage(
            sender="test", recipient=txn_agent.agent_id,
            message_type="REQUEST",
            content={"type": "TXN_SCORE_REQUEST", "txn": sim_txn},
        ))

    drift_msg = AgentMessage(
        sender="test", recipient=profile.agent_id,
        message_type="REQUEST",
        content={"type": "PROFILE_QUERY", "user_id": args.user_id},
    )
    drift_result = await profile.process(drift_msg)
    print(f"\nAfter 5 more transactions:")
    print(f"  Drift Score: {drift_result.content.get('drift_score', 0):.4f}")
    print(f"  Profile: {drift_result.content.get('profile', {})}")

    await profile.stop()
    await txn_agent.stop()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
