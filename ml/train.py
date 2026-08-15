import json
import logging
import math
import os
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.optim.lr_scheduler import CosineAnnealingLR

logger = logging.getLogger(__name__)

try:
    from torch_geometric.loader import DataLoader
    _has_pyg = True
except ImportError:
    DataLoader = None
    _has_pyg = False

try:
    from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, f1_score
    _has_sklearn = True
except ImportError:
    _has_sklearn = False


MODELS_DIR = Path("models")


class EarlyStopping:
    def __init__(self, patience: int = 10, min_delta: float = 0.001, monitor: str = "val_auc"):
        self.patience = patience
        self.min_delta = min_delta
        self.monitor = monitor
        self.counter = 0
        self.best_score = float("-inf")
        self.early_stop = False

    def step(self, score: float) -> bool:
        if score > self.best_score + self.min_delta:
            self.best_score = score
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        return self.early_stop


class GNNTrainer:
    def __init__(self, model, config: dict | None = None):
        self.model = model
        self.config = config or {}
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

        self.learning_rate = self.config.get("learning_rate", 0.001)
        self.weight_decay = self.config.get("weight_decay", 5e-4)
        self.pos_weight = self.config.get("pos_weight", 10.0)
        self.batch_size = self.config.get("batch_size", 32)
        self.patience = self.config.get("early_stop_patience", 10)

        self.optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        self.scheduler = CosineAnnealingLR(self.optimizer, T_max=50)
        self.criterion = torch.nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor([self.pos_weight], device=self.device)
        )
        self.early_stopping = EarlyStopping(patience=self.patience)

    def prepare_data(self, dataset, train_ratio: float = 0.8, val_ratio: float = 0.1):
        n = len(dataset)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        train_dataset = dataset[:n_train]
        val_dataset = dataset[n_train:n_train + n_val]
        test_dataset = dataset[n_train + n_val:]
        return train_dataset, val_dataset, test_dataset

    def create_dataloader(self, dataset, shuffle: bool = True) -> DataLoader:
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=shuffle)

    def _target_metadata(self, data):
        """Global (batched) target-user / target-txn indices for the readout.

        Convention (shared with scripts/benchmark_gnn.py): inside each ego-graph
        the target user is node 0 of the "user" type and its own transactions
        are the first ``data.target_txn_n`` nodes of the "transaction" type.
        Returns None when the metadata is absent → legacy mean-pool readout.
        """
        try:
            u = data.get("user")
            t = data.get("transaction")
            if u is None or t is None or not hasattr(u, "x") or u.x.size(0) == 0:
                return None
            if "ptr" in u:
                if "ptr" not in t or not hasattr(data, "target_txn_n"):
                    return None
                txn_n = data.target_txn_n
                if isinstance(txn_n, torch.Tensor) and txn_n.numel() == u.ptr[:-1].numel():
                    txn_n = txn_n
                else:
                    txn_n = torch.full((u.ptr[:-1].numel(),), int(txn_n), dtype=torch.long)
                return u.ptr[:-1], t.ptr[:-1], txn_n
            txn_n = torch.tensor([int(getattr(data, "target_txn_n", t.x.size(0)))], dtype=torch.long)
            return torch.zeros(1, dtype=torch.long), torch.zeros(1, dtype=torch.long), txn_n
        except (AttributeError, KeyError):
            return None

    def train_epoch(self, dataloader) -> float:
        self.model.train()
        total_loss = 0.0
        for data in dataloader:
            data = data.to(self.device)
            self.optimizer.zero_grad()
            meta = self._target_metadata(data)
            if meta is not None:
                out = self.model(data.x_dict, data.edge_index_dict, *meta)
            else:
                out = self.model(data.x_dict, data.edge_index_dict)
            y = data["user"].y if "user" in data.metadata() and hasattr(data["user"], "y") else None
            if y is None:
                continue
            y = y.view(-1, 1).float()
            loss = self.criterion(out[:, :1], y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            total_loss += loss.item()
        return total_loss / max(len(dataloader), 1)

    @torch.no_grad()
    def evaluate(self, dataloader) -> dict:
        self.model.eval()
        all_preds = []
        all_labels = []
        total_loss = 0.0

        for data in dataloader:
            data = data.to(self.device)
            meta = self._target_metadata(data)
            if meta is not None:
                out = self.model(data.x_dict, data.edge_index_dict, *meta)
            else:
                out = self.model(data.x_dict, data.edge_index_dict)
            y = data["user"].y if "user" in data.metadata() and hasattr(data["user"], "y") else None
            if y is None:
                continue
            y = y.view(-1, 1).float()
            loss = self.criterion(out[:, :1], y)
            total_loss += loss.item()

            probs = torch.sigmoid(out[:, :1])
            all_preds.extend(probs.cpu().numpy())
            all_labels.extend(y.cpu().numpy())

        if not all_labels:
            return {"loss": 0.0, "auc": 0.0, "auc_pr": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

        preds_np = [p[0] for p in all_preds] if all_preds and len(all_preds[0]) > 1 else all_preds
        labels_np = [l[0] for l in all_labels] if all_labels and len(all_labels[0]) > 1 else all_labels

        metrics = {"loss": total_loss / max(len(dataloader), 1)}

        if _has_sklearn and len(set(labels_np)) > 1:
            metrics["auc"] = round(roc_auc_score(labels_np, preds_np), 4)
            metrics["auc_pr"] = round(average_precision_score(labels_np, preds_np), 4)

            binary_preds = [1 if p >= 0.5 else 0 for p in preds_np]
            metrics["precision"] = round(precision_score(labels_np, binary_preds, zero_division=0), 4)
            metrics["recall"] = round(recall_score(labels_np, binary_preds, zero_division=0), 4)
            metrics["f1"] = round(f1_score(labels_np, binary_preds, zero_division=0), 4)

        return metrics

    def train(self, train_loader, val_loader, epochs: int = 100) -> dict:
        best_metrics = {}
        best_val_auc = 0.0

        for epoch in range(1, epochs + 1):
            train_loss = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)
            self.scheduler.step()

            val_auc = val_metrics.get("auc", 0.0)
            if val_auc > best_val_auc:
                best_val_auc = val_auc
                best_metrics = {"epoch": epoch, "train_loss": round(train_loss, 4), **val_metrics}
                self._save_checkpoint(self.model, "best_model.pt", val_metrics)

            if epoch % 10 == 0 or epoch == 1:
                logger.info(f"Epoch {epoch:3d}/{epochs} | Train loss: {train_loss:.4f} | "
                           f"Val AUC: {val_auc:.4f} | LR: {self.scheduler.get_last_lr()[0]:.6f}")

            if self.early_stopping.step(val_auc):
                logger.info(f"Early stopping triggered at epoch {epoch}")
                break

        logger.info(f"Training complete. Best val AUC: {best_val_auc:.4f}")
        return best_metrics

    def tune(self, train_loader, val_loader, n_trials: int = 20) -> dict:
        try:
            import optuna
        except ImportError:
            logger.warning("optuna not installed; skipping hyperparameter tuning")
            return self.train(train_loader, val_loader, epochs=50)

        def objective(trial):
            hp = {
                "hidden_channels": trial.suggest_categorical("hidden_channels", [32, 64, 128]),
                "num_layers": trial.suggest_int("num_layers", 1, 3),
                "dropout": trial.suggest_float("dropout", 0.1, 0.5),
                "learning_rate": trial.suggest_float("learning_rate", 1e-4, 1e-3, log=True),
                "pos_weight": trial.suggest_float("pos_weight", 5.0, 20.0),
            }
            from ml.model import PayShieldGNN
            model = PayShieldGNN(
                edge_types=[
                    ("user", "performed", "transaction"),
                    ("transaction", "to", "merchant"),
                    ("user", "used", "device"),
                    ("user", "transferred_to", "user"),
                    ("device", "shared_by", "user"),
                ],
                hidden_channels=hp["hidden_channels"],
                num_layers=hp["num_layers"],
                dropout=hp["dropout"],
            )
            trainer = GNNTrainer(model, {**self.config, **hp})
            trainer.model.to(self.device)
            metrics = trainer.train(train_loader, val_loader, epochs=30)
            return metrics.get("auc", 0.0)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=n_trials)

        logger.info(f"Best trial: {study.best_trial.params} (AUC: {study.best_value:.4f})")
        return study.best_trial.params

    def _save_checkpoint(self, model, filename: str, metrics: dict):
        os.makedirs(MODELS_DIR, exist_ok=True)
        path = MODELS_DIR / filename
        torch.save({
            "model_state_dict": model.state_dict(),
            "config": self.config,
            "metrics": metrics,
        }, path)
        logger.info(f"Checkpoint saved: {path}")

    def save_checkpoint(self, path: Path):
        os.makedirs(path.parent, exist_ok=True)
        torch.save({
            "model_state_dict": self.model.state_dict(),
            "config": self.config,
        }, path)

    def load_checkpoint(self, path: Path):
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.config = checkpoint.get("config", self.config)
        logger.info(f"Checkpoint loaded: {path}")
