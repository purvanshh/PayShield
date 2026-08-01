import pytest

from data.graph_builder import HeterogeneousGraphBuilder
from data.synthetic_upi import SyntheticUPIGenerator
from store.graph_db import GraphDB


@pytest.fixture(autouse=True)
def _hermetic_rate_limiter(monkeypatch):
    """Keep the IP rate-limit middleware in-memory and per-test.

    The module-level limiter otherwise binds to a real Redis (if one is
    running on localhost), making counters persist across tests.
    """
    from api.security import RateLimiter

    limiter = RateLimiter(redis_url=None)
    monkeypatch.setattr("api.security.rate_limiter", limiter)
    monkeypatch.setattr("api.main.rate_limiter", limiter)
    yield
    limiter._local_store.clear()


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
