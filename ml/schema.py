import logging
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)

try:
    from torch_geometric.data import HeteroData
    _has_pyg = True
except ImportError:
    HeteroData = None
    _has_pyg = False


class SchemaValidationError(Exception):
    pass


@dataclass
class GraphSchema:
    node_types: list[str] = field(default_factory=lambda: ["user", "merchant", "device", "transaction"])
    edge_types: list[tuple[str, str, str]] = field(default_factory=lambda: [
        ("user", "performed", "transaction"),
        ("transaction", "to", "merchant"),
        ("user", "used", "device"),
        ("user", "transferred_to", "user"),
        ("device", "shared_by", "user"),
    ])
    node_feature_dims: dict[str, int] = field(default_factory=lambda: {
        "user": 5,
        "merchant": 19,
        "device": 4,
        "transaction": 4,
    })
    num_classes: int = 2

    def get_feature_dim(self, node_type: str) -> int:
        return self.node_feature_dims.get(node_type, 0)

    def get_edge_types(self) -> list[tuple[str, str, str]]:
        return self.edge_types

    def to_dict(self) -> dict:
        return {
            "node_types": self.node_types,
            "edge_types": [[s, r, d] for s, r, d in self.edge_types],
            "node_feature_dims": self.node_feature_dims,
            "num_classes": self.num_classes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphSchema":
        edge_types_raw = data.get("edge_types", [])
        edge_types = [(s, r, d) for s, r, d in edge_types_raw]
        return cls(
            node_types=data.get("node_types", []),
            edge_types=edge_types,
            node_feature_dims=data.get("node_feature_dims", {}),
            num_classes=data.get("num_classes", 2),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "GraphSchema":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data.get("graph_schema", {}))


class HeteroDataSchemaValidator:
    def __init__(self, schema: GraphSchema):
        self.schema = schema

    def validate(self, data: "HeteroData") -> None:
        if not _has_pyg:
            logger.warning("PyG not available; schema validation skipped")
            return

        for ntype in self.schema.node_types:
            if ntype not in data.node_types:
                raise SchemaValidationError(f"Missing required node type: {ntype}")
            x = data[ntype].x
            expected_dim = self.schema.get_feature_dim(ntype)
            if x.size(-1) != expected_dim:
                raise SchemaValidationError(
                    f"Node type '{ntype}' feature dimension mismatch: "
                    f"got {x.size(-1)}, expected {expected_dim}"
                )

        for etype in self.schema.edge_types:
            if etype not in data.edge_types:
                logger.warning(f"Edge type {etype} not present in data (may be valid for isolated nodes)")

        for etype in data.edge_types:
            if etype not in self.schema.edge_types:
                raise SchemaValidationError(f"Unknown edge type: {etype}")

    def validate_batch(self, data_list: list["HeteroData"]) -> list[SchemaValidationError]:
        errors = []
        for i, data in enumerate(data_list):
            try:
                self.validate(data)
            except SchemaValidationError as e:
                errors.append(SchemaValidationError(f"Data[{i}]: {e}"))
        return errors
