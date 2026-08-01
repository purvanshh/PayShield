"""Live graph writer — keeps Neo4j and the NetworkX fallback in sync.

Called from the scoring hot path after features are recorded. Writes are
best-effort: a failure in any backend must never block or fail a payment.
"""

import logging

logger = logging.getLogger(__name__)

DEVICE_USERS_PREFIX = "device"
DEVICE_INDEX_TTL = 86400


def device_users_key(device_id: str) -> str:
    return f"{DEVICE_USERS_PREFIX}:{device_id}:users"


class GraphDBWriter:
    def __init__(self, neo4j=None, networkx_db=None, redis=None):
        self.neo4j = neo4j
        self.networkx_db = networkx_db
        self.redis = redis

    @property
    def backends(self) -> list[str]:
        active = []
        if self.neo4j is not None and getattr(self.neo4j, "_driver", None) is not None:
            active.append("neo4j")
        if self.networkx_db is not None:
            active.append("networkx")
        if self.redis is not None:
            active.append("redis_index")
        return active

    async def write_transaction(self, txn: dict, features: dict | None = None) -> dict:
        """Persist a live transaction to every available backend."""
        txn_id = txn.get("txn_id", "")
        user_id = txn.get("user_id", "")
        merchant_id = txn.get("merchant_id", "")
        device_id = txn.get("device_fingerprint") or "UNKNOWN_DEVICE"
        amount = float(txn.get("amount", 0.0))
        timestamp = txn.get("timestamp")
        txn_type = txn.get("txn_type", "P2M")
        counterparty = txn.get("counterparty_user_id")

        written = []
        try:
            if self.neo4j is not None and getattr(self.neo4j, "_driver", None) is not None:
                await self.neo4j.create_transaction_node(txn_id, amount, timestamp)
                await self.neo4j.link_user_to_txn(user_id, txn_id)
                await self.neo4j.link_merchant_to_txn(merchant_id, txn_id)
                await self.neo4j.link_device_to_txn(device_id, txn_id)
                if txn_type == "P2P" and counterparty:
                    await self.neo4j.link_p2p_transfer(user_id, counterparty, txn_id)
                written.append("neo4j")
        except Exception as e:
            logger.warning(f"graph_write_neo4j_failed: {e}")

        try:
            if self.networkx_db is not None:
                self.networkx_db.create_transaction_node(txn_id, amount, timestamp)
                self.networkx_db.link_user_to_txn(user_id, txn_id)
                self.networkx_db.link_merchant_to_txn(merchant_id, txn_id)
                self.networkx_db.link_device_to_txn(device_id, txn_id)
                if txn_type == "P2P" and counterparty:
                    self.networkx_db.link_p2p_transfer(user_id, counterparty, txn_id)
                written.append("networkx")
        except Exception as e:
            logger.warning(f"graph_write_networkx_failed: {e}")

        try:
            if self.redis is not None:
                await self.redis.sadd(device_users_key(device_id), user_id)
                await self.redis.expire(device_users_key(device_id), DEVICE_INDEX_TTL)
                written.append("redis_index")
        except Exception as e:
            logger.warning(f"graph_write_redis_index_failed: {e}")

        return {"backends": written}
