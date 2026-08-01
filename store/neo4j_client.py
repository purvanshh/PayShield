import logging
import os
from datetime import datetime, timezone

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

SCHEMA_CYPHER = """
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.user_id IS UNIQUE;

CREATE CONSTRAINT merchant_id_unique IF NOT EXISTS
FOR (m:Merchant) REQUIRE m.merchant_id IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

CREATE CONSTRAINT txn_id_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.txn_id IS UNIQUE;

CREATE INDEX user_risk_index IF NOT EXISTS
FOR (u:User) ON (u.risk_score);

CREATE INDEX txn_timestamp_index IF NOT EXISTS
FOR (t:Transaction) ON (t.timestamp);

CREATE INDEX merchant_category_index IF NOT EXISTS
FOR (m:Merchant) ON (m.category);

CREATE INDEX device_fingerprint_index IF NOT EXISTS
FOR (d:Device) ON (d.fingerprint_hash);
"""


class Neo4jGraphDB:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self._driver = None

    async def connect(self):
        logger.info(f"Connecting to Neo4j at {self.uri}")
        self._driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
        )
        await self._verify_connectivity()

    async def _verify_connectivity(self):
        async with self._driver.session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            if record and record["ok"] == 1:
                logger.info("Neo4j connection verified")
            else:
                raise ConnectionError("Neo4j connectivity check failed")

    async def close(self):
        if self._driver:
            await self._driver.close()

    async def initialize_schema(self):
        async with self._driver.session() as session:
            for statement in SCHEMA_CYPHER.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    await session.run(stmt + ";")
            logger.info("Neo4j schema initialized")

    async def create_user(self, user_id: str, features: dict | None = None):
        props = {
            "user_id": user_id,
            "risk_score": features.get("risk_score", 0.0) if features else 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (u:User {user_id: $user_id})
                SET u += $props
                """,
                user_id=user_id,
                props=props,
            )

    async def create_merchant(self, merchant_id: str, features: dict | None = None):
        props = {
            "merchant_id": merchant_id,
            "category": features.get("category", "unknown") if features else "unknown",
            "country": features.get("country", "UNKNOWN") if features else "UNKNOWN",
            "risk_level": features.get("risk_level", "low") if features else "low",
        }
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (m:Merchant {merchant_id: $merchant_id})
                SET m += $props
                """,
                merchant_id=merchant_id,
                props=props,
            )

    async def create_device(self, device_id: str, fingerprint_hash: str, features: dict | None = None):
        props = {
            "device_id": device_id,
            "fingerprint_hash": fingerprint_hash,
            "is_emulator": features.get("is_emulator", False) if features else False,
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (d:Device {device_id: $device_id})
                SET d += $props
                """,
                device_id=device_id,
                props=props,
            )

    async def create_transaction_node(self, txn_id: str, amount: float, timestamp: datetime | float | str | None = None):
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        props = {
            "txn_id": txn_id,
            "amount": amount,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        }
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (t:Transaction {txn_id: $txn_id})
                SET t += $props
                """,
                txn_id=txn_id,
                props=props,
            )

    async def link_user_to_txn(self, user_id: str, txn_id: str):
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (u:User {user_id: $user_id})
                MERGE (t:Transaction {txn_id: $txn_id})
                MERGE (u)-[:PERFORMED]->(t)
                """,
                user_id=user_id,
                txn_id=txn_id,
            )

    async def link_merchant_to_txn(self, merchant_id: str, txn_id: str):
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (m:Merchant {merchant_id: $merchant_id})
                MERGE (t:Transaction {txn_id: $txn_id})
                MERGE (t)-[:AT]->(m)
                """,
                merchant_id=merchant_id,
                txn_id=txn_id,
            )

    async def link_device_to_txn(self, device_id: str, txn_id: str, fingerprint_hash: str | None = None):
        if not device_id or device_id == "UNKNOWN_DEVICE":
            return
        props = {"fingerprint_hash": fingerprint_hash or device_id}
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (d:Device {device_id: $device_id})
                SET d += $props
                WITH d
                MERGE (t:Transaction {txn_id: $txn_id})
                MERGE (t)-[:USED]->(d)
                """,
                device_id=device_id,
                props=props,
                txn_id=txn_id,
            )

    async def link_p2p_transfer(self, from_user_id: str, to_user_id: str, txn_id: str):
        async with self._driver.session() as session:
            await session.run(
                """
                MERGE (u1:User {user_id: $from_user_id})
                MERGE (u2:User {user_id: $to_user_id})
                MERGE (t:Transaction {txn_id: $txn_id})
                MERGE (u1)-[:TRANSFERRED_TO]->(t)
                MERGE (t)-[:TRANSFERRED_TO]->(u2)
                """,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                txn_id=txn_id,
            )

    async def create_transaction(self, txn_id: str, user_id: str, merchant_id: str, amount: float, device_id: str | None = None):
        await self.create_transaction_node(txn_id, amount)
        await self.link_user_to_txn(user_id, txn_id)
        await self.link_merchant_to_txn(merchant_id, txn_id)
        if device_id:
            await self.link_device_to_txn(device_id, txn_id)

    async def link_user_device(self, user_id: str, device_id: str):
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (u:User {user_id: $user_id})
                MATCH (d:Device {device_id: $device_id})
                MERGE (u)-[:USES]->(d)
                """,
                user_id=user_id,
                device_id=device_id,
            )

    async def get_user_risk_score(self, user_id: str) -> float | None:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (u:User {user_id: $user_id}) RETURN u.risk_score AS score",
                user_id=user_id,
            )
            record = await result.single()
            return record["score"] if record else None

    async def get_transaction_history(self, user_id: str, limit: int = 100) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (u:User {user_id: $user_id})-[:PERFORMED]->(t:Transaction)-[:AT]->(m:Merchant)
                RETURN t.txn_id AS txn_id, t.amount AS amount,
                       t.timestamp AS timestamp, m.merchant_id AS merchant_id,
                       m.category AS category
                ORDER BY t.timestamp DESC
                LIMIT $limit
                """,
                user_id=user_id,
                limit=limit,
            )
            return [dict(record) async for record in result]

    async def get_merchant_network(self, merchant_id: str, hops: int = 2) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH path = (m:Merchant {{merchant_id: $merchant_id}})<-[:AT]-(:Transaction)<-[:PERFORMED]-(u:User)-[:PERFORMED]->(:Transaction)-[:AT]->(related:Merchant)
                WHERE m <> related
                RETURN related.merchant_id AS merchant_id,
                       related.category AS category,
                       COUNT(DISTINCT u) AS shared_users,
                       COUNT(DISTINCT u) AS strength
                ORDER BY shared_users DESC
                LIMIT 20
                """,
                merchant_id=merchant_id,
            )
            return [dict(record) async for record in result]

    async def batch_ingest_transactions(self, transactions: list[dict]):
        async with self._driver.session() as session:
            batch_size = 500
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                await session.run(
                    """
                    UNWIND $batch AS txn
                    MERGE (u:User {user_id: txn.user_id})
                    MERGE (m:Merchant {merchant_id: txn.merchant_id})
                    CREATE (t:Transaction {
                        txn_id: txn.txn_id,
                        amount: txn.amount,
                        timestamp: datetime(txn.timestamp)
                    })
                    CREATE (u)-[:PERFORMED]->(t)
                    CREATE (t)-[:AT]->(m)
                    """,
                    batch=batch,
                )
                logger.info(f"Batch {i // batch_size + 1}: {len(batch)} transactions ingested")

    async def get_ego_graph(self, node_id: str, node_label: str = "User", hops: int = 2) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH path = (n:{node_label} {{{node_label.lower()}_id: $node_id}})-[*1..$hops]-(related)
                RETURN path
                LIMIT 1000
                """,
                node_id=node_id,
                hops=hops,
            )
            return [dict(record) async for record in result]

    async def run_query(self, cypher: str, params: dict | None = None) -> list[dict]:
        async with self._driver.session() as session:
            result = await session.run(cypher, params or {})
            return [dict(record) async for record in result]
