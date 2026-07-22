from engine.statistical_filter import StatisticalFilter, StatisticalResult
from engine.graph_model import PayShieldGNN
from engine.graph_feature_engine import GraphFeatureEngine
from engine.explainer import GNNExplainerWrapper, SHAPBridge


class EnsembleScorer:
    def __init__(self, graph_db, config: dict | None = None):
        self.config = config or {}
        self.statistical_filter = StatisticalFilter(self.config.get("statistical", {}))
        self.gnn_model = PayShieldGNN(
            hidden_channels=self.config.get("model", {}).get("hidden_channels", 64),
            num_layers=self.config.get("model", {}).get("num_layers", 2),
            dropout=self.config.get("model", {}).get("dropout", 0.3),
        )
        self.graph_engine = GraphFeatureEngine(graph_db)
        self.explainer = GNNExplainerWrapper(self.gnn_model)
        self.shap_bridge = SHAPBridge(self.gnn_model)
        self.block_threshold = self.config.get("thresholds", {}).get("block_probability", 0.85)

    def score(self, txn, feature_store):
        txn_data = txn if isinstance(txn, dict) else (txn.model_dump() if hasattr(txn, "model_dump") else txn.__dict__)

        layer1_result = self.statistical_filter.evaluate(txn_data, feature_store)

        if layer1_result.decision == "BLOCK":
            return {
                "fraud_probability": 1.0,
                "decision": "BLOCK",
                "layer_triggered": "L1_STATISTICAL",
                "evidence": {"triggered_rules": layer1_result.triggered_rules},
                "latency_ms": 0.0,
                "model_version": "1.0.0",
            }

        if layer1_result.decision == "ALLOW":
            return {
                "fraud_probability": 0.0,
                "decision": "ALLOW",
                "layer_triggered": "L1_STATISTICAL",
                "evidence": {"triggered_rules": []},
                "latency_ms": 0.0,
                "model_version": "1.0.0",
            }

        subgraph = self.graph_engine.extract_ego_graph(
            txn_data["user_id"], txn_data["merchant_id"], hops=2
        )

        if subgraph.number_of_nodes() == 0:
            return {
                "fraud_probability": 0.0,
                "decision": "ALLOW",
                "layer_triggered": "L2_GNN",
                "evidence": {"error": "empty_subgraph"},
                "latency_ms": 0.0,
                "model_version": "1.0.0",
            }

        pyg_data = self.graph_engine.hydrate_features(subgraph, feature_store)

        explanation = self.explainer.explain(
            {ntype: pyg_data[ntype].x for ntype in pyg_data.node_types if hasattr(pyg_data[ntype], "x")},
            {etype: pyg_data[etype].edge_index for etype in pyg_data.edge_types},
        )

        fraud_prob = explanation["fraud_probability"]

        if fraud_prob >= self.block_threshold:
            decision = "BLOCK"
        elif fraud_prob >= 0.5:
            decision = "REVIEW"
        else:
            decision = "ALLOW"

        return {
            "fraud_probability": fraud_prob,
            "decision": decision,
            "layer_triggered": "L2_GNN",
            "evidence": {
                "layer1_rules": layer1_result.triggered_rules,
                "layer1_chi2": layer1_result.benford_chi2,
                "gnn_explanation": explanation,
                "subgraph_size": subgraph.number_of_nodes(),
                "subgraph_edges": subgraph.number_of_edges(),
            },
            "latency_ms": 0.0,
            "model_version": "1.0.0",
        }
