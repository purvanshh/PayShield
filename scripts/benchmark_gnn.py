"""
Benchmark the L2 heterogeneous GNN (PayShieldGNN) end-to-end:
  - builds a heterogeneous ego-graph dataset from the synthetic UPI generator
  - trains the GNN (HeteroConv + SAGEConv, 2 layers, hidden 64)
  - evaluates AUC-ROC / PR-AUC / F1 / FPR@0.90 recall on a user-disjoint test split
  - benchmarks per-ego-graph inference latency on CPU (p50/p90/p95/p99)
  - trains an edge-free MLP baseline on the same target-user features

Everything is measured on synthetic data (the only data this repo ships), and
every number is computed at runtime — nothing is hardcoded.

Usage:
    python scripts/benchmark_gnn.py [--users 6000 --merchants 500 --txns 18000
                                    --epochs 40 --latency-runs 300 --seed 42]

Graph schema (heterogeneous):
    node types:    user (5 features) | merchant (19) | device (4) | transaction (4)
    edge types:    user --performed--> transaction
                   transaction --to--> merchant
                   user --used--> device
                   user --transferred_to--> user   (P2P; recipients are derived
                                                   deterministically from the
                                                   merchant id, since the
                                                   generator emits only merchant)
                   device --shared_by--> user      (mule-ring signal: a device
                                                   used by multiple users)

Label: 1 if the target user has any fraud transaction (per-sample ego-graph).
"""

import argparse
import hashlib
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.optim.lr_scheduler import CosineAnnealingLR
from sklearn.metrics import (
    auc as sk_auc,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from torch_geometric.data import HeteroData
from torch_geometric.loader import DataLoader

from data.synthetic.generator import SyntheticUPIGenerator
from ml.model import PayShieldGNN, FraudClassifier

EDGE_TYPES = [
    ("user", "performed", "transaction"),
    ("transaction", "to", "merchant"),
    ("user", "used", "device"),
    ("user", "transferred_to", "user"),
    ("device", "shared_by", "user"),
]

MCC_ORDER = [
    "food", "travel", "utilities", "fashion", "groceries",
    "entertainment", "health", "education", "transport", "rent",
    "recharge", "insurance", "investment", "cashback", "other",
]


def user_features(users: dict, uid: str) -> list[float]:
    u = users[uid]
    return [
        u["credit_score"] / 900.0,
        min(u["account_age_days"] / 1200.0, 1.0),
        u["kyc_tier"] / 3.0,
        min(u["avg_monthly_txn_count"] / 100.0, 1.0),
        min(u["device_count"] / 3.0, 1.0),
    ]


def merchant_features(merchants: dict, mid: str) -> list[float]:
    m = merchants[mid]
    one_hot = [1.0 if c == m["mcc_code"] else 0.0 for c in MCC_ORDER]
    return one_hot + [
        min(m["avg_txn_amount"] / 10000.0, 1.0),
        m["refund_rate"],
        min(m["account_age_days"] / 1500.0, 1.0),
        m["city_tier"] / 4.0,
    ]


def device_features(devices: dict, did: str) -> list[float]:
    d = devices[did]
    major, minor = (int(p) for p in d["app_version"].split(".")[:2])
    return [
        1.0 if d["os_family"] == "android" else 0.0,
        major / 8.0,
        minor / 9.0,
        1.0 if d["is_emulator"] else 0.0,
    ]


def transaction_features(row) -> list[float]:
    ts = row["timestamp"]
    return [
        min(row["amount"] / 20000.0, 1.0),
        ts.hour / 24.0,
        1.0 if ts.weekday() >= 5 else 0.0,
        1.0 if ts.day <= 2 else 0.0,  # salary-day proxy
    ]


class EgoGraphDataset:
    """One HeteroData per target user (ego-graph with neighbors)."""

    def __init__(self, df, users, merchants, devices,
                 min_history: int = 3, max_txns: int = 10, max_neighbors: int = 5):
        self.txn_by_user = defaultdict(list)
        for _, row in df.iterrows():
            self.txn_by_user[row["user_id"]].append(row)
        self.users, self.merchants, self.devices = users, merchants, devices
        self.min_history, self.max_txns, self.max_neighbors = min_history, max_txns, max_neighbors
        self.n_users = len(users)
        self._recipient_cache = {}
        self._device_owner = {dev["device_id"]: dev["user_id"] for dev in devices.values()}

    def recipient_for(self, mid: str) -> str:
        if mid not in self._recipient_cache:
            h = int(hashlib.md5(mid.encode()).hexdigest(), 16)
            self._recipient_cache[mid] = f"U{str(h % self.n_users).zfill(6)}"
        return self._recipient_cache[mid]

    def build(self, target: str) -> HeteroData | None:
        txns = sorted(self.txn_by_user.get(target, []), key=lambda r: r["timestamp"])
        if len(txns) < self.min_history:
            return None

        txns = txns[-self.max_txns:]

        neighbors = set()
        for r in txns:
            if r["txn_type"] == "P2P":
                neighbors.add(self.recipient_for(r["merchant_id"]))
        for d in {r["device_fingerprint"] for r in txns}:
            owner = self._device_owner.get(d)
            if owner is not None and owner != target:
                neighbors.add(owner)
        neighbors = list(neighbors - {target})[: self.max_neighbors]

        neighbor_txns: dict[str, list] = {}
        for uid in neighbors:
            nt = sorted(self.txn_by_user.get(uid, []), key=lambda r: r["timestamp"])
            if nt:
                neighbor_txns[uid] = nt[-3:]
        all_txns = txns + [r for lst in neighbor_txns.values() for r in lst]

        merchant_ids = {r["merchant_id"] for r in all_txns}
        device_ids = {r["device_fingerprint"] for r in all_txns}

        node_ids: dict[str, list[str]] = {t: [] for t in ["user", "merchant", "device", "transaction"]}
        index: dict[tuple[str, str], int] = {}

        def add(node_type: str, nid: str) -> int:
            if (node_type, nid) not in index:
                index[(node_type, nid)] = len(node_ids[node_type])
                node_ids[node_type].append(nid)
            return index[(node_type, nid)]

        add("user", target)
        for uid in neighbors:
            add("user", uid)
        for mid in merchant_ids:
            add("merchant", mid)
        for did in device_ids:
            add("device", did)

        edges = defaultdict(list)
        for r in all_txns:
            ti = add("transaction", r["txn_id"])
            ui = index[("user", r["user_id"])]
            mi = index[("merchant", r["merchant_id"])]
            di = index[("device", r["device_fingerprint"])]
            edges[("user", "performed", "transaction")] += [ui, ti]
            edges[("transaction", "to", "merchant")] += [ti, mi]
            edges[("user", "used", "device")] += [ui, di]
            edges[("device", "shared_by", "user")] += [di, ui]
            if r["txn_type"] == "P2P":
                rid = self.recipient_for(r["merchant_id"])
                if (("user", rid) in index or rid == target) and r["user_id"] != rid:
                    if ("user", rid) not in index:
                        add("user", rid)
                    ri = index[("user", rid)]
                    edges[("user", "transferred_to", "user")] += [ui, ri]

        data = HeteroData()
        data["user"].x = torch.tensor([user_features(self.users, u) for u in node_ids["user"]], dtype=torch.float)
        data["merchant"].x = torch.tensor([merchant_features(self.merchants, m) for m in node_ids["merchant"]], dtype=torch.float)
        data["device"].x = torch.tensor([device_features(self.devices, d) for d in node_ids["device"]], dtype=torch.float)
        data["transaction"].x = torch.tensor([transaction_features(r) for r in all_txns], dtype=torch.float)

        for et in EDGE_TYPES:
            src_type, _, dst_type = et
            if et in edges:
                src = torch.tensor(edges[et][0::2], dtype=torch.long)
                dst = torch.tensor(edges[et][1::2], dtype=torch.long)
                data[et].edge_index = torch.stack([src, dst])
            else:
                data[et].edge_index = torch.zeros((2, 0), dtype=torch.long)

        is_fraud = any(bool(r["is_fraud"]) for r in txns)
        data["user"].y = torch.tensor([1.0 if is_fraud else 0.0], dtype=torch.float)
        data.label = 1.0 if is_fraud else 0.0
        data.num_nodes_by_type = {t: len(v) for t, v in node_ids.items()}
        # Readout metadata: the target user is always node 0 of its graph, and
        # the target's own transactions are the first ``len(txns)`` transaction
        # nodes (all_txns = target txns + neighbor txns). PyG batches preserve
        # per-graph node order, so per-sample slices derive from the batch ptrs.
        data.target_txn_n = len(txns)
        return data


def target_readout_meta(data, device) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor] | None:
    """Global (batched) indices of each sample's target user and its transactions.

    Uses the PyG batch ``ptr`` when present (DataLoader output); for a bare
    HeteroData the target user is node 0 and the target transactions start at 0.
    Returns None when the metadata is unavailable (legacy mean-pool fallback).
    """
    u = data["user"] if "user" in data.node_types else None
    t = data["transaction"] if "transaction" in data.node_types else None
    if u is None or t is None or u.x.size(0) == 0:
        return None
    if "ptr" in u:
        if "ptr" not in t or not hasattr(data, "target_txn_n"):
            return None
        txn_n = data.target_txn_n
        if isinstance(txn_n, torch.Tensor) and txn_n.numel() == u.ptr[:-1].numel():
            txn_n = txn_n.to(device)
        else:
            txn_n = torch.full((u.ptr[:-1].numel(),), int(txn_n), dtype=torch.long, device=device)
        return u.ptr[:-1].to(device), t.ptr[:-1].to(device), txn_n
    target_user_idx = torch.zeros(1, dtype=torch.long, device=device)
    starts = torch.zeros(1, dtype=torch.long, device=device)
    txn_n = torch.tensor([int(getattr(data, "target_txn_n", t.x.size(0)))],
                         dtype=torch.long, device=device)
    return target_user_idx, starts, txn_n


def train_loop(model, train_loader, val_loader, device, epochs, pos_weight=10.0, patience=8,
               lr=1e-3):
    """Train with early stopping + checkpoint selection on val PR-AUC.

    PR-AUC is the lead metric for imbalanced fraud: AUC-ROC peaks on models
    that rank the legitimate majority well, whose checkpoints are not the
    best fraud-finders. Returns the best val PR-AUC achieved.
    """
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    sched = CosineAnnealingLR(opt, T_max=max(epochs, 1))
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], device=device))
    best_val_pr, best_state, no_improve = 0.0, None, 0

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        for data in train_loader:
            data = data.to(device)
            opt.zero_grad()
            meta = target_readout_meta(data, device)
            if meta is not None:
                out = model(data.x_dict, data.edge_index_dict, *meta)
            else:
                out = model(data.x_dict, data.edge_index_dict)
            y = data.label.unsqueeze(1).to(device)
            loss = criterion(out[:, :1], y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            opt.step()
            total_loss += loss.item()
        sched.step()

        _, val_metrics = evaluate(model, val_loader, device)
        val_pr = val_metrics["auc_pr"]
        if val_pr > best_val_pr + 1e-4:
            best_val_pr = val_pr
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1
        if epoch % 10 == 0 or epoch == 1:
            print(f"  epoch {epoch:3d}/{epochs}  loss {total_loss / max(len(train_loader), 1):.4f}  val_pr_auc {val_pr:.4f}")
        if no_improve >= patience:
            print(f"  early stop at epoch {epoch}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return best_val_pr


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    probs, labels = [], []
    for data in loader:
        data = data.to(device)
        meta = target_readout_meta(data, device)
        if meta is not None:
            out = model(data.x_dict, data.edge_index_dict, *meta)
        else:
            out = model(data.x_dict, data.edge_index_dict)
        probs.extend(torch.sigmoid(out[:, 0]).cpu().tolist())
        labels.extend(data.label.tolist())
    if len(set(labels)) < 2:
        return 0.0, {}
    p, l = probs, labels
    metrics = {
        "auc_roc": round(roc_auc_score(l, p), 4),
        "auc_pr": round(average_precision_score(l, p), 4),
    }
    fpr, tpr, thr = roc_curve(l, p)
    target_recall = 0.90
    valid = [i for i in range(len(tpr)) if tpr[i] >= target_recall]
    if valid:
        i = min(valid, key=lambda i: fpr[i])
        metrics["fpr_at_0.90_recall"] = round(fpr[i], 4)
        metrics["threshold_at_0.90_recall"] = round(float(thr[i]), 4)
    for t in (0.3, 0.5, 0.7):
        pred = [1 if x >= t else 0 for x in p]
        metrics[f"f1@{t}"] = round(f1_score(l, pred, zero_division=0), 4)
        metrics[f"precision@{t}"] = round(precision_score(l, pred, zero_division=0), 4)
        metrics[f"recall@{t}"] = round(recall_score(l, pred, zero_division=0), 4)
    return metrics["auc_roc"], metrics


@torch.no_grad()
def benchmark_latency(model, loader, device, warmup=50, runs=300):
    model.eval()
    samples = [d.to(device) for d in loader.dataset]
    metas = [target_readout_meta(d, device) for d in samples]
    for _ in range(warmup):
        for d in samples[:16]:
            model(d.x_dict, d.edge_index_dict)
    times = []
    for i in range(runs):
        d = samples[i % len(samples)]
        meta = metas[i % len(samples)]
        t0 = time.perf_counter()
        if meta is not None:
            model(d.x_dict, d.edge_index_dict, *meta)
        else:
            model(d.x_dict, d.edge_index_dict)
        times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    n = len(times)
    q = lambda pct: times[min(int(pct * n / 100), n - 1)]
    sizes = [(sum(d.num_nodes_by_type.values()), d[("user", "performed", "transaction")].edge_index.size(1)) for d in samples]
    return {
        "mean_ms": round(statistics.fmean(times), 3),
        "p50_ms": round(q(50), 3),
        "p90_ms": round(q(90), 3),
        "p95_ms": round(q(95), 3),
        "p99_ms": round(q(99), 3),
        "max_ms": round(times[-1], 3),
        "runs": n,
        "graph_nodes_min": min(s[0] for s in sizes),
        "graph_nodes_median": int(statistics.median(s[0] for s in sizes)),
        "graph_nodes_max": max(s[0] for s in sizes),
        "graph_edges_median": int(statistics.median(s[1] for s in sizes)),
    }


def hyperparameter_sweep(train_graphs, val_graphs, device, n_trials=8, sweep_epochs=25, seed=42):
    """Optuna sweep maximizing val PR-AUC (the lead fraud metric).

    Search space: hidden 32/64/128, layers 2/3, dropout 0.0/0.3/0.5,
    pos_weight 5/10/20, learning rate 1e-3..1e-2, batch size 4/8/16.
    Returns the best trial's params.
    """
    try:
        import optuna
    except ImportError:
        print("optuna not installed; skipping sweep")
        return {}

    def objective(trial):
        hp = {
            "hidden": trial.suggest_categorical("hidden", [32, 64, 128]),
            "layers": trial.suggest_categorical("layers", [2, 3]),
            "dropout": trial.suggest_categorical("dropout", [0.0, 0.3, 0.5]),
            "pos_weight": trial.suggest_categorical("pos_weight", [5, 10, 20]),
            "lr": trial.suggest_float("lr", 1e-3, 1e-2, log=True),
            "batch": trial.suggest_categorical("batch", [4, 8, 16]),
        }
        model = PayShieldGNN(edge_types=EDGE_TYPES, hidden_channels=hp["hidden"],
                             num_layers=hp["layers"], dropout=hp["dropout"])
        model.to(device)
        with torch.no_grad():
            warm = train_graphs[0].to(device)
            model(warm.x_dict, warm.edge_index_dict)
        train_loader = DataLoader(train_graphs, batch_size=hp["batch"], shuffle=True)
        val_loader = DataLoader(val_graphs, batch_size=hp["batch"], shuffle=False)
        return train_loop(model, train_loader, val_loader, device, epochs=sweep_epochs,
                          pos_weight=hp["pos_weight"], patience=6, lr=hp["lr"])

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    print(f"sweep best trial: {study.best_trial.params} (val PR-AUC {study.best_value:.4f})")
    return study.best_trial.params


def main():
    ap = argparse.ArgumentParser(description="Measure L2 GNN performance (synthetic data)")
    ap.add_argument("--users", type=int, default=6000)
    ap.add_argument("--merchants", type=int, default=500)
    ap.add_argument("--txns", type=int, default=18000)
    ap.add_argument("--fraud-ratio", type=float, default=0.05)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--sweep-trials", type=int, default=0,
                    help="run an optuna PR-AUC hyperparameter sweep with this many trials")
    ap.add_argument("--sweep-epochs", type=int, default=25,
                    help="epochs per optuna trial")
    ap.add_argument("--latency-runs", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=str, default="models/gnn_benchmark_results.json")
    ap.add_argument("--save-model", action="store_true",
                    help="persist the best GNN state dict to models/production/current.pt")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Generating synthetic data: {args.users} users, {args.merchants} merchants, {args.txns} txns...")

    gen = SyntheticUPIGenerator(n_users=args.users, n_merchants=args.merchants,
                                n_transactions=args.txns, fraud_ratio=args.fraud_ratio,
                                seed=args.seed)
    t0 = time.time()
    df = gen.generate()
    print(f"  generated {len(df)} txns ({int(df['is_fraud'].sum())} fraud) in {time.time() - t0:.1f}s")

    print("Building ego-graph dataset (user-disjoint split)...")
    dataset = EgoGraphDataset(df, gen.users, gen.merchants, gen.devices)
    candidates = sorted(df["user_id"].unique())
    graphs = []
    for uid in candidates:
        g = dataset.build(uid)
        if g is not None:
            graphs.append((uid, g))
    rng = torch.Generator().manual_seed(args.seed)
    perms = torch.randperm(len(graphs), generator=rng).tolist()
    n_tr = int(len(graphs) * 0.8)
    n_va = int(len(graphs) * 0.1)
    train = [graphs[i][1] for i in perms[:n_tr]]
    val = [graphs[i][1] for i in perms[n_tr:n_tr + n_va]]
    test = [graphs[i][1] for i in perms[n_tr + n_va:]]
    print(f"  graphs: train {len(train)} val {len(val)} test {len(test)} "
          f"(positives: {sum(g.label for g in test)} test)")
    assert sum(1 for g in test if g.label) >= 10, "too few test positives — increase data size"

    batch = args.batch_size
    hp = {}
    if args.sweep_trials > 0:
        print(f"\n=== Optuna sweep ({args.sweep_trials} trials, {args.sweep_epochs} epochs, metric=val PR-AUC) ===")
        hp = hyperparameter_sweep(train, val, device, n_trials=args.sweep_trials,
                                  sweep_epochs=args.sweep_epochs, seed=args.seed)

    batch = hp.get("batch", batch)
    hidden = hp.get("hidden", 64)
    num_layers = hp.get("layers", 2)
    dropout = hp.get("dropout", 0.3)
    pos_weight = hp.get("pos_weight", 10.0)
    lr = hp.get("lr", 1e-3)
    print(f"final config: hidden={hidden} layers={num_layers} dropout={dropout} "
          f"pos_weight={pos_weight} lr={lr} batch_size={batch} epochs={args.epochs}")

    train_loader = DataLoader(train, batch_size=batch, shuffle=True)
    val_loader = DataLoader(val, batch_size=batch, shuffle=False)
    test_loader = DataLoader(test, batch_size=batch, shuffle=False)

    print(f"\n=== L2 GNN (HeteroConv + SAGEConv, hidden={hidden}, layers={num_layers}) ===")
    gnn = PayShieldGNN(edge_types=EDGE_TYPES, hidden_channels=hidden, num_layers=num_layers,
                       dropout=dropout)
    gnn.to(device)
    with torch.no_grad():
        warm = train[0].to(device)
        gnn(warm.x_dict, warm.edge_index_dict)  # initializes lazy SAGEConv params
    print(f"parameters: {gnn.count_parameters():,}")
    t0 = time.time()
    best_val = train_loop(gnn, train_loader, val_loader, device, args.epochs,
                          pos_weight=pos_weight, lr=lr)
    train_secs = round(time.time() - t0, 1)
    print(f"training done in {train_secs}s (best val AUC {best_val:.4f})")
    _, gnn_test = evaluate(gnn, test_loader, device)
    latency = benchmark_latency(gnn, test_loader, device, runs=args.latency_runs)
    print(f"test metrics: {json.dumps(gnn_test, indent=2)}")
    print(f"latency: mean {latency['mean_ms']} ms  p50 {latency['p50_ms']}  p90 {latency['p90_ms']}  "
          f"p99 {latency['p99_ms']}  (graph nodes median {latency['graph_nodes_median']}, "
          f"edges median {latency['graph_edges_median']})")

    print(f"\n=== Baseline: edge-free MLP on target-user features (5 dims) ===")
    X = torch.tensor([user_features(gen.users, graphs[i][0]) for i in perms], dtype=torch.float)
    y = torch.tensor([graphs[i][1].label for i in perms], dtype=torch.float).unsqueeze(1)
    mlp = FraudClassifier(input_dim=5, hidden_dim=64, output_dim=1)
    mlp.to(device)
    opt = torch.optim.Adam(mlp.parameters(), lr=1e-3, weight_decay=5e-4)
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([10.0], device=device))
    Xtr, ytr = X[perms[:n_tr]].to(device), y[perms[:n_tr]].to(device)
    Xva, yva = X[perms[n_tr:n_tr + n_va]].to(device), y[perms[n_tr:n_tr + n_va]].to(device)
    Xte, yte = X[perms[n_tr + n_va:]].to(device), y[perms[n_tr + n_va:]].to(device)
    mlp.train()
    best_va, best_ws = 0.0, None
    for epoch in range(args.epochs):
        opt.zero_grad()
        loss = criterion(mlp(Xtr), ytr)
        loss.backward()
        opt.step()
        mlp.eval()
        with torch.no_grad():
            p = torch.sigmoid(mlp(Xva)).squeeze(1).cpu().tolist()
            l = yva.squeeze(1).cpu().tolist()
        va = roc_auc_score(l, p) if len(set(l)) > 1 else 0.0
        mlp.train()
        if va > best_va:
            best_va = va
            best_ws = {k: v.detach().cpu().clone() for k, v in mlp.state_dict().items()}
    mlp.load_state_dict(best_ws)
    mlp.eval()
    with torch.no_grad():
        probs = torch.sigmoid(mlp(Xte)).squeeze(1).cpu().tolist()
        labels = yte.squeeze(1).cpu().tolist()
    mlp_test = {
        "auc_roc": round(roc_auc_score(labels, probs), 4),
        "auc_pr": round(average_precision_score(labels, probs), 4),
    }
    fpr, tpr, thr = roc_curve(labels, probs)
    valid = [i for i in range(len(tpr)) if tpr[i] >= 0.90]
    if valid:
        i = min(valid, key=lambda i: fpr[i])
        mlp_test["fpr_at_0.90_recall"] = round(fpr[i], 4)
    for t in (0.3, 0.5, 0.7):
        pred = [1 if x >= t else 0 for x in probs]
        mlp_test[f"f1@{t}"] = round(f1_score(labels, pred, zero_division=0), 4)
    print(f"baseline test metrics: {json.dumps(mlp_test, indent=2)}")

    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": str(device),
        "lead_metric": "PR-AUC — for imbalanced fraud, AUC-ROC is dominated by the legitimate majority; PR-AUC measures the minority (fraud) class directly",
        "data": {"source": "synthetic UPI generator (scripts/generate_synthetic_data.py)",
                 "users": args.users, "merchants": args.merchants,
                 "transactions": args.txns, "fraud_ratio": args.fraud_ratio, "seed": args.seed},
        "graph_schema": {
            "node_types": {"user": 5, "merchant": 19, "device": 4, "transaction": 4},
            "edge_types": [list(et) for et in EDGE_TYPES],
        },
        "gnn": {"architecture": "HeteroConv + SAGEConv (mean aggr) + target-user readout "
                                "with transaction attention, MLP head",
                "hyperparameters": {"hidden_channels": hidden, "num_layers": num_layers,
                                    "dropout": dropout, "pos_weight": pos_weight,
                                    "learning_rate": lr, "batch_size": batch},
                "sweep": {"trials": args.sweep_trials, "epochs_per_trial": args.sweep_epochs,
                          "metric": "val PR-AUC"},
                "parameters": gnn.count_parameters(),
                "train_epochs_effective": "early-stopped, max " + str(args.epochs),
                "train_seconds": train_secs,
                "test_split": {"graphs": len(test), "positives": int(sum(g.label for g in test))},
                "test_metrics": gnn_test,
                "inference_latency_ms_cpu": latency},
        "baseline": {"architecture": "edge-free MLP (FraudClassifier) on 5 target-user features",
                     "test_metrics": mlp_test,
                     "pr_auc_lift_vs_gnn": round(gnn_test["auc_pr"] / max(mlp_test["auc_pr"], 1e-9), 1)},
        "limitations": [
            "trained on synthetic data; real UPI traffic has different seasonality",
            "P2P recipients derived deterministically from merchant id (generator emits no recipient)",
            "burst/ATO patterns carry no graph-representable signal in the base feature schema "
            "(velocity, location distance), bounding absolute PR-AUC",
        ],
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out}")

    if args.save_model:
        from ml.registry import ModelRegistry
        from pathlib import Path as _P
        registry = ModelRegistry()
        artifact = _P(registry.production_dir) / f"payshield_gnn_v1.pt"
        torch.save({"state_dict": gnn.state_dict(),
                    "hidden_channels": 64, "num_layers": 2, "dropout": 0.3,
                    "edge_types": [list(et) for et in EDGE_TYPES],
                    "metrics": {"auc_pr": gnn_test["auc_pr"], "auc_roc": gnn_test["auc_roc"]}},
                   artifact)
        symlink = _P(registry.production_dir) / "current.pt"
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        symlink.symlink_to(artifact.name)
        print(f"Model artifact saved: {artifact} (current.pt -> {artifact.name})")

    print("\n=== Summary ===")
    print(f"GNN test:      PR-AUC {gnn_test['auc_pr']} (lead)  AUC-ROC {gnn_test['auc_roc']}  "
          f"FPR@0.90recall {gnn_test['fpr_at_0.90_recall']}")
    print(f"MLP baseline:  PR-AUC {mlp_test['auc_pr']}  AUC-ROC {mlp_test['auc_roc']}  "
          f"FPR@0.90recall {mlp_test.get('fpr_at_0.90_recall', 'n/a')}")
    print(f"PR-AUC lift vs. edge-free baseline: {gnn_test['auc_pr'] / max(mlp_test['auc_pr'], 1e-9):.1f}x")
    print(f"Latency (CPU): p50 {latency['p50_ms']} ms  p90 {latency['p90_ms']} ms  "
          f"p99 {latency['p99_ms']} ms")


if __name__ == "__main__":
    main()
