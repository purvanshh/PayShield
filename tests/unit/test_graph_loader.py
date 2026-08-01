import pytest

from engine.graph_loader import (
    FEATURE_EXTRACTORS,
    HeteroDataBatch,
    HeteroGraphConverter,
    _extract_device_features,
    _extract_merchant_features,
    _extract_transaction_features,
    _extract_user_features,
)


def _build_graph():
    import networkx as nx

    graph = nx.Graph()
    graph.add_node("U1", node_type="User", credit_score=750, account_age_days=730,
                   avg_monthly_txn_count=40, device_count=2, kyc_tier=2)
    graph.add_node("M1", node_type="Merchant", category_code=5411, avg_txn_amount=2500,
                   refund_rate=0.02, account_age_days=365, benford_chi2=15.5)
    graph.add_node("D1", node_type="Device", os_family="Android", is_emulator=0,
                   first_seen_days=90)
    graph.add_node("T1", node_type="Transaction", amount=5000, timestamp_hour=14,
                   timestamp_day=3, is_high_risk_merchant=1)
    graph.add_edge("U1", "T1", edge_type="performed")
    graph.add_edge("T1", "M1", edge_type="to")
    graph.add_edge("U1", "D1", edge_type="used")
    graph.add_node("U2", node_type="User", credit_score=600)
    graph.add_edge("U2", "T1", edge_type="performed")
    return graph


class TestFeatureExtractors:
    def test_user_features(self):
        features = _extract_user_features(
            {"credit_score": 750, "account_age_days": 730, "avg_monthly_txn_count": 40,
             "device_count": 2, "kyc_tier": 2}
        )
        assert features[0] == pytest.approx(0.75, abs=0.01)
        assert features[1] == pytest.approx(2.0, abs=0.01)
        assert len(features) == 5

    def test_user_defaults(self):
        features = _extract_user_features({})
        assert features == [0.6, 0.0, 0.0, 0.1, 0.0]

    def test_merchant_features(self):
        features = _extract_merchant_features(
            {"category_code": 5400, "avg_txn_amount": 10000, "refund_rate": 0.5,
             "account_age_days": 365, "benford_chi2": 50}
        )
        assert len(features) == 5
        assert features[0] == 1.0
        assert features[-1] == pytest.approx(0.5, abs=0.01)

    def test_device_features(self):
        assert _extract_device_features({"os_family": "Android", "is_emulator": 1,
                                         "first_seen_days": 30}) == [1.0, 1.0, 1.0]
        assert _extract_device_features({"os_family": "iOS"})[0] == 0.0

    def test_transaction_features(self):
        features = _extract_transaction_features(
            {"amount": 5000, "timestamp_hour": 23, "timestamp_day": 7,
             "is_high_risk_merchant": 1}
        )
        assert features[0] == pytest.approx(0.5, abs=0.01)
        assert features[1] == pytest.approx(1.0, abs=0.01)
        assert features[3] == 1.0

    def test_extractors_registry(self):
        assert set(FEATURE_EXTRACTORS) == {"User", "Merchant", "Device", "Transaction"}


class TestHeteroGraphConverter:
    def test_convert_basic(self):
        converter = HeteroGraphConverter()
        data = converter.convert(_build_graph())
        assert data["User"].x.shape == (2, 5)
        assert data["Merchant"].x.shape == (1, 5)
        assert data["Device"].x.shape == (1, 3)
        assert data["Transaction"].x.shape == (1, 4)
        assert data[("User", "performed", "Transaction")].edge_index.shape[0] == 2
        assert data[("Transaction", "to", "Merchant")].edge_index.shape[0] == 2
        assert data[("User", "used", "Device")].edge_index.shape[0] == 2
        assert data[("User", "transferred_to", "User")].edge_index.shape == (2, 0)

    def test_convert_empty_graph(self):
        import networkx as nx

        converter = HeteroGraphConverter()
        data = converter.convert(nx.Graph())
        assert data["User"].x.shape == (0, 5)
        assert data[("User", "performed", "Transaction")].edge_index.shape == (2, 0)

    def test_convert_unknown_node_type_skipped(self):
        import networkx as nx

        graph = nx.Graph()
        graph.add_node("X1", node_type="UnknownType", weird=1)
        converter = HeteroGraphConverter()
        data = converter.convert(graph)
        assert data["User"].x.shape == (0, 5)

    def test_target_user_marked(self):
        converter = HeteroGraphConverter()
        graph = _build_graph()
        data = converter.convert(graph, target_user_id="U1")
        assert data["User"].target_node.tolist() == [0]

    def test_convert_with_default_node_type(self):
        import networkx as nx

        graph = nx.Graph()
        graph.add_node("T1", amount=100)
        converter = HeteroGraphConverter()
        data = converter.convert(graph)
        assert data["Transaction"].x.shape == (1, 4)


class TestHeteroDataBatch:
    def test_single_list_returns_same(self):
        converter = HeteroGraphConverter()
        data = converter.convert(_build_graph())
        assert HeteroDataBatch.batch([data]) is data

    def test_multi_batch(self):
        converter = HeteroGraphConverter()
        data1 = converter.convert(_build_graph())
        data2 = converter.convert(_build_graph())
        batch = HeteroDataBatch.batch([data1, data2])
        assert batch is not data1
        assert batch["User"].x.shape[0] == 4

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            HeteroDataBatch.batch([])

    def test_batch_to_device(self):
        converter = HeteroGraphConverter()
        data = converter.convert(_build_graph())
        moved = HeteroDataBatch.batch_to_device(data, "cpu")
        assert moved is data
