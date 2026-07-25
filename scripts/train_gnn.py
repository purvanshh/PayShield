import argparse
import logging

import torch

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
    parser = argparse.ArgumentParser(description="Train PayShield GNN model")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--tune", action="store_true", help="Run hyperparameter tuning")
    parser.add_argument("--n-trials", type=int, default=20)
    parser.add_argument("--epochs-per-trial", type=int, default=30)
    args = parser.parse_args()

    config = {
        "hidden_channels": args.hidden,
        "num_layers": args.layers,
        "dropout": args.dropout,
        "learning_rate": args.lr,
        "batch_size": args.batch_size,
        "pos_weight": 10.0,
        "weight_decay": 5e-4,
        "early_stop_patience": 10,
    }

    model = PayShieldGNN(
        edge_types=EDGE_TYPES,
        hidden_channels=args.hidden,
        num_layers=args.layers,
        dropout=args.dropout,
    )

    total_params = model.count_parameters()
    print(f"Model parameters: {total_params:,}")
    print(f"Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}")

    trainer = GNNTrainer(model, config)

    from ml.train import MODELS_DIR
    from pathlib import Path
    import time

    dummy_data = _create_dummy_data()
    train_dataset, val_dataset, test_dataset = trainer.prepare_data(dummy_data)
    train_loader = trainer.create_dataloader(train_dataset, shuffle=True)
    val_loader = trainer.create_dataloader(val_dataset, shuffle=False)

    if args.tune:
        print(f"\nHyperparameter tuning ({args.n_trials} trials)...")
        best_hp = trainer.tune(train_loader, val_loader, n_trials=args.n_trials)
        print(f"Best hyperparameters: {best_hp}")
    else:
        print(f"\nTraining for {args.epochs} epochs...")
        start = time.time()
        metrics = trainer.train(train_loader, val_loader, epochs=args.epochs)
        elapsed = time.time() - start
        print(f"\nTraining completed in {elapsed:.1f}s")
        print(f"Best validation metrics:")
        for k, v in metrics.items():
            print(f"  {k}: {v}")
        print(f"\nModel checkpoint saved to: {MODELS_DIR / 'best_model.pt'}")


def _create_dummy_data():
    try:
        from torch_geometric.data import HeteroData
        import torch

        data = HeteroData()
        data["user"].x = torch.randn(10, 5)
        data["user"].y = torch.randint(0, 2, (10, 1)).float()
        data["merchant"].x = torch.randn(5, 19)
        data["device"].x = torch.randn(3, 4)
        data["transaction"].x = torch.randn(8, 4)
        data[("user", "performed", "transaction")].edge_index = torch.randint(0, 10, (2, 8)).long()
        data[("transaction", "to", "merchant")].edge_index = torch.randint(0, 5, (2, 8)).long()
        data[("user", "used", "device")].edge_index = torch.randint(0, 3, (2, 6)).long()

        for et in EDGE_TYPES:
            if et not in data.edge_types:
                data[et].edge_index = torch.zeros((2, 0), dtype=torch.long)

        return [data]
    except ImportError:
        logger.warning("PyG not available; creating empty dataset")
        return []


if __name__ == "__main__":
    main()
