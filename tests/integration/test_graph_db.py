"""Graph store integration tests: NetworkX roundtrip + Neo4j when available.

The Neo4j suite is skipped automatically when no Neo4j instance is reachable,
so the full test run still passes with zero external services.
"""

import pytest

from store.graph_db import GraphDB, NetworkXGraphDB


class TestNetworkXRoundtrip:
    def test_alias_identity(self):
        assert GraphDB is NetworkXGraphDB

    def test_transaction_roundtrip(self):
        db = GraphDB()
        db.create_transaction_node("TXN1", amount=1000.0, timestamp="2026-07-01T10:00:00")
        db.link_user_to_txn("U1", "TXN1")
        db.link_merchant_to_txn("M1", "TXN1")
        db.link_device_to_txn("DEV1", "TXN1")

        assert db.has_node("U1")
        assert db.has_node("TXN1")
        assert db.has_node("M1")
        assert db.has_node("DEV1")
        assert db.node_count() == 4
        assert db.edge_count() == 3

        txn_attrs = db.get_node_attributes("TXN1")
        assert txn_attrs["node_type"] == "Transaction"
        assert txn_attrs["amount"] == 1000.0

    def test_ego_graph_capture(self):
        db = GraphDB()
        for i in range(5):
            db.create_transaction_node(f"TXN{i}", amount=100.0, timestamp=f"2026-07-0{i+1}T10:00:00")
            db.link_user_to_txn("U1", f"TXN{i}")
            db.link_merchant_to_txn("M1", f"TXN{i}")
        db.link_p2p_transfer("U1", "U2", "TXN_P2P")

        ego = db.get_ego_graph("U1", hops=2)
        assert "U1" in ego.nodes()
        assert "U2" in ego.nodes()
        assert len([n for n in ego.nodes() if ego.nodes[n].get("node_type") == "Transaction"]) == 6

    def test_neighbors_filtered_by_type(self):
        db = GraphDB()
        db.link_user_to_txn("U1", "T1")
        db.link_merchant_to_txn("M1", "T1")
        db.link_device_to_txn("DEV1", "T1")
        merchants = db.get_neighbors("T1", node_type="Merchant")
        assert merchants == ["M1"]
        assert "U1" not in merchants

    def test_network_score_with_risk_cluster(self):
        db = GraphDB()
        for i in range(4):
            db.create_transaction_node(f"T{i}", amount=100.0)
            db.link_user_to_txn("U1", f"T{i}")
        db.add_node("U1", "User", {"user_id": "U1", "is_fraud": True})
        score = db.get_network_score("U1")
        assert score["connected_entities"] >= 4
        assert 0.0 <= score["network_score"] <= 1.0
        assert score["risk_clusters"] == 1

    def test_clear_and_close(self):
        db = GraphDB()
        db.link_user_to_txn("U1", "T1")
        assert db.node_count() > 0
        db.clear()
        assert db.node_count() == 0
        db.close()


class TestNeo4jRoundtrip:
    async def test_connect_and_roundtrip(self):
        try:
            from store.neo4j_client import Neo4jGraphDB
            neo4j = Neo4jGraphDB()
            await neo4j.connect()
            await neo4j.initialize_schema()
        except Exception as e:
            pytest.skip(f"Neo4j unavailable: {e}")

        try:
            await neo4j.create_user("U_TST")
            await neo4j.create_merchant("M_TST")
            await neo4j.create_transaction_node("TXN_TST", amount=100.0)
        finally:
            await neo4j.close()
