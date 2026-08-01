"""L2 GNN hot-path inference service.

Loads the production GNN once (lazily) and serves conditional inference:
ego-graph extraction -> feature hydration -> time-guarded prediction.
Every failure mode degrades to a typed L2Status instead of raising.
"""

import asyncio
import logging
import threading
import time
from pathlib import Path

from engine.constants import L2Status

logger = logging.getLogger(__name__)

# Inference runs inside the container on a Docker Desktop aarch64 CPU build,
# where tiny-matrix kernel launches cost ~50x more than on native CPU. The
# 20ms figure from the plan was host-measured; 40ms keeps SUCCESS dominant
# in the container while still bounding worst-case latency.
L2_TIMEOUT_MS = 40.0
MIN_GRAPH_NODES = 2

try:
    import torch
    from torch_geometric.data import HeteroData
    from ml.model import PayShieldGNN
    from engine.graph_feature_engine import GraphFeatureEngine, extract_ego_graph_live
    _deps_ready = True
except ImportError:
    torch = None
    HeteroData = None
    PayShieldGNN = None
    GraphFeatureEngine = None
    extract_ego_graph_live = None
    _deps_ready = False

EDGE_TYPES = [
    ("user", "performed", "transaction"),
    ("transaction", "to", "merchant"),
    ("user", "used", "device"),
    ("user", "transferred_to", "user"),
    ("device", "shared_by", "user"),
]

_LOAD_LOCK = threading.Lock()


class L2InferenceService:
    def __init__(self, model_path: Path | None = None, hidden_channels: int = 64,
                 num_layers: int = 2, dropout: float = 0.3, timeout_ms: float = L2_TIMEOUT_MS):
        self.model_path = model_path
        self.hidden_channels = hidden_channels
        self.num_layers = num_layers
        self.dropout = dropout
        self.timeout_ms = timeout_ms
        self._model = None
        self._load_error: str | None = None
        self._feature_engine = GraphFeatureEngine(graph_db=None) if GraphFeatureEngine else None

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load_model(self):
        if not _deps_ready:
            self._load_error = "torch/PyG unavailable"
            return
        if self._model is not None:
            return
        if self.model_path is None or not Path(self.model_path).exists():
            try:
                from ml.registry import ModelRegistry
                resolved = ModelRegistry().get_production_model()
                if resolved is not None and resolved.exists():
                    self.model_path = resolved
                else:
                    self._load_error = f"model artifact missing: {self.model_path}"
                    logger.warning(self._load_error)
                    return
            except Exception as e:
                self._load_error = f"model artifact missing: {e}"
                logger.warning(self._load_error)
                return
        with _LOAD_LOCK:
            if self._model is not None:
                return
            try:
                import torch
                if not torch.cuda.is_available():
                    torch.set_num_threads(1)
                model = PayShieldGNN(
                    edge_types=EDGE_TYPES,
                    hidden_channels=self.hidden_channels,
                    num_layers=self.num_layers,
                    dropout=self.dropout,
                )
                state = torch.load(self.model_path, map_location="cpu")
                if isinstance(state, dict) and "state_dict" in state:
                    state = state["state_dict"]
                model.load_state_dict(state)
                model.eval()
                self._model = model
                self._load_error = None
                logger.info(f"L2 GNN loaded from {self.model_path}")
            except Exception as e:
                self._load_error = f"load failed: {e}"
                logger.error(self._load_error)

    async def predict(self, graph, user_id: str, merchant_id: str,
                      device_id: str | None = None) -> dict:
        """Run the full L2 pipeline against a live ego graph.

        Returns a dict: {status, fraud_probability, latency_ms, nodes, edges}
        """
        start = time.perf_counter()
        if self._model is None:
            self.load_model()
            if self._model is None:
                return {"status": L2Status.MODEL_UNAVAILABLE.value,
                        "fraud_probability": 0.0,
                        "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                        "nodes": 0, "edges": 0}

        if graph is None or graph.number_of_nodes() < MIN_GRAPH_NODES:
            return {"status": L2Status.SKIPPED_NO_GRAPH.value,
                    "fraud_probability": 0.0,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "nodes": graph.number_of_nodes() if graph is not None else 0,
                    "edges": graph.number_of_edges() if graph is not None else 0}

        try:
            data = self._feature_engine.hydrate_features(graph, feature_store=None)
            x_dict = {ntype: t for ntype, t in data.x_dict.items()}
            edge_index_dict = {k: v for k, v in data.edge_index_dict.items()}

            prob, timed_out = await asyncio.to_thread(
                self._model.predict_proba_safe, x_dict, edge_index_dict, self.timeout_ms
            )
            if timed_out:
                return {"status": L2Status.TIMEOUT.value,
                        "fraud_probability": 0.0,
                        "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                        "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}

            return {"status": L2Status.SUCCESS.value,
                    "fraud_probability": round(prob, 6),
                    "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()}
        except Exception as e:
            logger.error(f"L2 inference failed: {e}")
            return {"status": L2Status.ERROR.value,
                    "fraud_probability": 0.0,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 3),
                    "nodes": graph.number_of_nodes() if graph is not None else 0,
                    "edges": graph.number_of_edges() if graph is not None else 0}
