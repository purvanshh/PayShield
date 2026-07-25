import argparse
import logging

import torch
from torch_geometric.data import HeteroData

from ml.model import PayShieldGNN
from ml.train import GNNTrainer

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
    parser = argparse.ArgumentParser(description="Evaluate PayShield GNN model")
    parser.add_argument("--checkpoint", default="models/best_model.pt")
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.3)
    args = parser.parse_args()

    model = PayShieldGNN(
        edge_types=EDGE_TYPES,
        hidden_channels=args.hidden,
        num_layers=args.layers,
        dropout=args.dropout,
    )

    trainer = GNNTrainer(model)

    try:
        trainer.load_checkpoint(args.checkpoint)
        print(f"Model loaded from {args.checkpoint}")
    except FileNotFoundError:
        print(f"No checkpoint found at {args.checkpoint}. Using untrained model.")

    print(f"Model parameters: {model.count_parameters():,}")

    dummy_data = HeteroData()
    dummy_data["user"].x = torch.randn(10, 5)
    dummy_data["merchant"].x = torch.randn(5, 19)
    dummy_data["device"].x = torch.randn(3, 4)
    dummy_data["transaction"].x = torch.randn(8, 4)
    dummy_data[("user", "performed", "transaction")].edge_index = torch.randint(0, 10, (2, 8)).long()
    dummy_data[("transaction", "to", "merchant")].edge_index = torch.randint(0, 5, (2, 8)).long()
    dummy_data[("user", "used", "device")].edge_index = torch.randint(0, 3, (2, 6)).long()
    dummy_data[("user", "transferred_to", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)
    dummy_data[("device", "shared_by", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)

    trainer.model.eval()
    with torch.no_grad():
        out = trainer.model(dummy_data.x_dict, dummy_data.edge_index_dict)
        probs = torch.sigmoid(out)
        pred = torch.argmax(out, dim=-1)

    print(f"\nForward pass:")
    print(f"  Output shape: {list(out.shape)}")
    print(f"  Probabilities: {probs.tolist()}")
    print(f"  Predicted class: {pred.tolist()}")

    param_stats = model.get_param_stats()
    print(f"\nParameter breakdown:")
    for name, count in param_stats.items():
        print(f"  {name}: {count:,}")


if __name__ == "__main__":
    main()
