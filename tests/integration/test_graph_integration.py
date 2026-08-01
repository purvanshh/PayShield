
from data.graph_builder import HeterogeneousGraphBuilder
from data.synthetic_upi import SyntheticUPIGenerator
from engine.graph_feature_engine import GraphFeatureEngine
from engine.graph_model import PayShieldGNN
from store.graph_db import GraphDB


class TestEndToEndGraphPipeline:
    def test_build_and_score(self):
        gen = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=500, fraud_ratio=0.05)
        df = gen.generate()

        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
        builder.add_p2p_edges(df)
        builder.add_device_sharing_edges()
        pyg_data = builder.to_pyg_data()

        assert pyg_data["user"].x.shape[0] > 0
        assert pyg_data["merchant"].x.shape[0] > 0
        assert pyg_data["device"].x.shape[0] > 0
        assert len([et for et in pyg_data.edge_types if et[1] == "performed"]) > 0

        model = PayShieldGNN(hidden_channels=16, num_layers=2)
        x_dict = {nt: pyg_data[nt].x for nt in pyg_data.node_types}
        edge_index_dict = {et: pyg_data[et].edge_index for et in pyg_data.edge_types}
        out = model(x_dict, edge_index_dict)
        assert out.shape[0] == 1

    def test_ego_graph_extraction(self):
        gen = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=500)
        df = gen.generate()

        graph_db = GraphDB()
        builder = HeterogeneousGraphBuilder()
        builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
        graph_db.graph = builder.graph.copy()

        engine = GraphFeatureEngine(graph_db)
        first_user = df["user_id"].iloc[0]
        first_merchant = df["merchant_id"].iloc[0]
        ego = engine.extract_ego_graph(first_user, first_merchant, hops=2)

        assert ego.number_of_nodes() > 0
        pyg_data = engine.hydrate_features(ego, None)
        assert pyg_data is not None
