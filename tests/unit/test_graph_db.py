import pytest

from store.graph_db import GraphDB
from data.graph_builder import HeterogeneousGraphBuilder


class TestGraphDB:
    def test_add_and_get_node(self):
        db = GraphDB()
        db.add_node("U1", "user", {"credit_score": 750})
        assert db.graph.has_node("U1")
        assert db.graph.nodes["U1"]["node_type"] == "user"
        assert db.graph.nodes["U1"]["credit_score"] == 750

    def test_add_edge(self):
        db = GraphDB()
        db.add_node("U1", "user", {})
        db.add_node("T1", "transaction", {})
        db.add_edge("U1", "T1", "performed")
        assert db.graph.has_edge("U1", "T1")

    def test_ego_graph_empty(self):
        db = GraphDB()
        ego = db.get_ego_graph("nonexistent")
        assert ego.number_of_nodes() == 0

    def test_ego_graph_single_hop(self):
        db = GraphDB()
        db.graph.add_node("U1", node_type="user")
        db.graph.add_node("T1", node_type="transaction")
        db.graph.add_node("M1", node_type="merchant")
        db.graph.add_edge("U1", "T1", edge_type="performed")
        db.graph.add_edge("T1", "M1", edge_type="to")
        ego = db.get_ego_graph("U1", hops=1)
        assert ego.has_node("U1")
        assert ego.has_node("T1")

    def test_ego_graph_two_hops(self):
        db = GraphDB()
        db.graph.add_node("U1", node_type="user")
        db.graph.add_node("T1", node_type="transaction")
        db.graph.add_node("M1", node_type="merchant")
        db.graph.add_edge("U1", "T1", edge_type="performed")
        db.graph.add_edge("T1", "M1", edge_type="to")
        ego = db.get_ego_graph("U1", hops=2)
        assert ego.has_node("M1")
