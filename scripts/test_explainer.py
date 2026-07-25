import argparse
import logging

import torch
from torch_geometric.data import HeteroData

from ml.explainer import GNNExplainerWrapper, ExplanationFormatter
from ml.model import PayShieldGNN
from ml.schema import GraphSchema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EDGE_TYPES = [
    ("user", "performed", "transaction"),
    ("transaction", "to", "merchant"),
    ("user", "used", "device"),
    ("user", "transferred_to", "user"),
    ("device", "shared_by", "user"),
]


def main():
    parser = argparse.ArgumentParser(description="Test GNNExplainer on sample data")
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()

    model = PayShieldGNN(
        edge_types=EDGE_TYPES,
        hidden_channels=args.hidden,
        num_layers=args.layers,
        dropout=args.dropout,
    )

    data = HeteroData()
    data["user"].x = torch.randn(5, 5)
    data["merchant"].x = torch.randn(3, 19)
    data["device"].x = torch.randn(2, 4)
    data["transaction"].x = torch.randn(4, 4)
    data[("user", "performed", "transaction")].edge_index = torch.tensor([
        [0, 0, 1, 1, 2, 3],
        [0, 1, 1, 2, 2, 3],
    ], dtype=torch.long)
    data[("transaction", "to", "merchant")].edge_index = torch.tensor([
        [0, 1, 2, 3],
        [0, 0, 1, 2],
    ], dtype=torch.long)
    data[("user", "used", "device")].edge_index = torch.tensor([
        [0, 1, 2],
        [0, 0, 1],
    ], dtype=torch.long)
    data[("user", "transferred_to", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)
    data[("device", "shared_by", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)

    schema = GraphSchema()
    try:
        from ml.schema import HeteroDataSchemaValidator
        validator = HeteroDataSchemaValidator(schema)
        validator.validate(data)
        print("Schema validation: PASSED")
    except Exception as e:
        print(f"Schema validation: {e}")

    print(f"\nModel forward pass:")
    with torch.no_grad():
        out = model(data.x_dict, data.edge_index_dict)
        probs = torch.sigmoid(out)
        print(f"  Output: {probs.tolist()}")

    print(f"\nRunning GNNExplainer ({args.epochs} epochs)...")
    explainer = GNNExplainerWrapper(model, epochs=args.epochs)
    result = explainer.explain(data)

    formatted = ExplanationFormatter.format(result)
    print(f"\n{formatted}")

    print(f"\nSubgraph size: {result.subgraph_size}")
    print(f"Fraud pattern: {result.fraud_pattern.value}")
    print(f"Node mask available: {result.node_mask is not None}")
    print(f"Edge mask available: {result.edge_mask is not None}")


if __name__ == "__main__":
    main()
