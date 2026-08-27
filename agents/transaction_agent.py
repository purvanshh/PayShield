import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from agents.base import AgentConfig, BaseAgent
from agents.message import AgentMessage, MessageType

logger = logging.getLogger(__name__)

# A scored order below this threshold is a clean pass; above it the order
# already carries elevated return risk from the scorer.
ELEVATED_SCORE = 0.5


class TransactionAnalysisAgent(BaseAgent):
    """Watches scored return-risk orders and maintains an order-level ledger.

    Consumes ``RETURN_RISK_SCORED`` events (emitted by the worker feed from
    the audit chain) and computes a per-user verdict from the transaction
    layer: order velocity, COD exposure, amount-vs-category risk and the
    merchant's own return rate (read live from Redis). Emits
    ``TXN_ANALYSIS_RESULT`` back to the caller with components and evidence.
    """

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(config or AgentConfig(agent_id="transaction_agent", agent_type="TRANSACTION"))
        self._txn_log: dict[str, list[dict]] = defaultdict(list)

    async def process(self, message: AgentMessage) -> AgentMessage:
        msg_type = message.content.get("type", "")
        if msg_type == "RETURN_RISK_SCORED":
            return await self._handle_score_request(message)
        elif msg_type == "ORDER_VELOCITY_QUERY":
            return await self._handle_velocity_query(message)
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE,
            content={"status": "ignored", "reason": f"unknown type: {msg_type}"},
            correlation_id=message.message_id,
        )

    async def _handle_score_request(self, message: AgentMessage) -> AgentMessage:
        order = message.content.get("order", {})
        user_id = message.content.get("user_id", "") or order.get("user_id", "")
        merchant_id = order.get("merchant_id", "")

        velocity_score = self._velocity_analysis(user_id)
        cod_score = self._cod_exposure(user_id)
        amount_score = self._amount_analysis(order)
        merchant_score = await self._merchant_risk(merchant_id)

        weighted = (
            velocity_score * 0.35
            + cod_score * 0.25
            + amount_score * 0.20
            + merchant_score * 0.20
        )

        response = {
            "type": "TXN_ANALYSIS_RESULT",
            "user_id": user_id,
            "order_id": order.get("order_id", ""),
            "risk_score": round(weighted, 4),
            "elevated": weighted > ELEVATED_SCORE,
            "components": {
                "order_velocity": velocity_score,
                "cod_exposure": cod_score,
                "amount_anomaly": amount_score,
                "merchant_return_rate": merchant_score,
            },
            "evidence": {
                "velocity": self._velocity_evidence(user_id),
                "cod": self._cod_evidence(user_id),
                "merchant": await self._merchant_evidence(merchant_id),
            },
        }

        if user_id:
            self._txn_log[user_id].append({
                "order_id": order.get("order_id", ""),
                "amount": float(order.get("amount", 0) or 0),
                "merchant_id": merchant_id,
                "cod_flag": bool(order.get("cod_flag", False)),
                "category": order.get("category", ""),
                "score": float(order.get("score", 0) or 0),
                "timestamp": datetime.utcnow().isoformat(),
            })
            if len(self._txn_log[user_id]) > 200:
                self._txn_log[user_id] = self._txn_log[user_id][-200:]

        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content=response,
            correlation_id=message.message_id,
        )

    async def _handle_velocity_query(self, message: AgentMessage) -> AgentMessage:
        user_id = message.content.get("user_id", "")
        window_minutes = int(message.content.get("window_minutes", 60))
        orders = self._orders_in_window(user_id, timedelta(minutes=window_minutes))
        return AgentMessage(
            sender=self.config.agent_id, recipient=message.sender,
            message_type=MessageType.RESPONSE, content={
                "type": "ORDER_VELOCITY_RESULT", "user_id": user_id,
                "orders": orders, "count": len(orders),
            },
            correlation_id=message.message_id,
        )

    # ------------------------------------------------------------------ #
    # analysis                                                            #
    # ------------------------------------------------------------------ #

    def _velocity_analysis(self, user_id: str) -> float:
        """Order placement velocity in a 5-minute window (serial ordering)."""
        recent = self._orders_in_window(user_id, timedelta(minutes=5))
        count = len(recent)
        if count < 3:
            return 0.0
        return min(1.0, count / 20.0)

    def _cod_exposure(self, user_id: str) -> float:
        """Share of the user's recent orders that are COD."""
        recent = self._txn_log.get(user_id, [])[-20:]
        if not recent:
            return 0.0
        cod = sum(1 for o in recent if o.get("cod_flag"))
        return cod / len(recent)

    def _amount_analysis(self, order: dict) -> float:
        amount = float(order.get("amount", 0) or 0)
        if amount <= 0:
            return 0.0
        category = (order.get("category", "") or "").lower()
        category_baseline = {
            "fashion": 0.32, "electronics": 0.12, "grocery": 0.04,
            "home": 0.18, "beauty": 0.15, "sports": 0.20,
        }.get(category, 0.15)
        # High amount relative to the category's return baseline.
        return min(1.0, (amount / 50000.0) * (0.5 + category_baseline))

    async def _merchant_risk(self, merchant_id: str) -> float:
        """Live merchant return rate from the Redis feature store."""
        if not merchant_id:
            return 0.1
        try:
            key = f"return_risk:merchant:{merchant_id}"
            data = await self._redis_get_hash(key)
            rate = float(data.get("return_rate_30d", 0.0) or 0.0) if data else 0.0
            return min(1.0, rate / 0.5)
        except Exception as e:  # nosec B110 - merchant lookup failure degrades
            logger.debug("merchant risk lookup failed for %s: %s", merchant_id, e)
            return 0.1

    def _orders_in_window(self, user_id: str, window: timedelta) -> list[dict]:
        now = datetime.utcnow()
        return [
            o for o in self._txn_log.get(user_id, [])
            if now - datetime.fromisoformat(o["timestamp"]) <= window
        ]

    def _velocity_evidence(self, user_id: str) -> list[str]:
        recent = self._orders_in_window(user_id, timedelta(minutes=5))
        if len(recent) > 3:
            return [f"{len(recent)} orders placed in the last 5 minutes"]
        return []

    def _cod_evidence(self, user_id: str) -> list[str]:
        recent = self._txn_log.get(user_id, [])[-20:]
        if not recent:
            return []
        cod = sum(1 for o in recent if o.get("cod_flag"))
        if cod:
            return [f"{cod}/{len(recent)} recent orders are cash-on-delivery"]
        return []

    async def _merchant_evidence(self, merchant_id: str) -> list[str]:
        try:
            data = await self._redis_get_hash(f"return_risk:merchant:{merchant_id}")
            if data and data.get("return_rate_30d"):
                return [f"merchant return rate {float(data['return_rate_30d']):.0%}"]
        except Exception:  # nosec B110 - evidence collection is best-effort
            pass
        return []

    # ------------------------------------------------------------------ #
    # redis helpers                                                       #
    # ------------------------------------------------------------------ #

    async def _redis_get_hash(self, key: str) -> dict[str, Any]:
        if self._heartbeat_redis is None:
            return {}
        try:
            return await self._heartbeat_redis.hgetall(key)
        except Exception:  # nosec B110
            return {}