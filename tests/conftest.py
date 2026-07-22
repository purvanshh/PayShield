import pytest

from data.synthetic_upi import SyntheticUPIGenerator
from data.graph_builder import HeterogeneousGraphBuilder
from store.graph_db import GraphDB


@pytest.fixture(scope="session")
def synthetic_data():
    gen = SyntheticUPIGenerator(n_users=100, n_merchants=50, n_transactions=1000, fraud_ratio=0.05)
    df = gen.generate()
    return df, gen


@pytest.fixture(scope="session")
def graph_db(synthetic_data):
    df, gen = synthetic_data
    builder = HeterogeneousGraphBuilder()
    builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
    builder.add_p2p_edges(df)
    builder.add_device_sharing_edges()
    db = GraphDB()
    db.graph = builder.graph.copy()
    return db


@pytest.fixture(scope="session")
def pyg_data(synthetic_data):
    df, gen = synthetic_data
    builder = HeterogeneousGraphBuilder()
    builder.build_from_transactions(df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
    builder.add_p2p_edges(df)
    builder.add_device_sharing_edges()
    return builder.to_pyg_data()
