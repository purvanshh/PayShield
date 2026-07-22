import argparse
import copy

import numpy as np
import torch
from sklearn.metrics import roc_auc_score, average_precision_score

from data.synthetic_upi import SyntheticUPIGenerator
from data.graph_builder import HeterogeneousGraphBuilder
from engine.graph_model import PayShieldGNN


def inject_noise(df, lat_noise_std: float = 0.0, lon_noise_std: float = 0.0,
                 device_swap_prob: float = 0.0, amount_noise_pct: float = 0.0):
    noisy = df.copy()

    if lat_noise_std > 0:
        noisy["lat"] += np.random.normal(0, lat_noise_std, len(noisy))
    if lon_noise_std > 0:
        noisy["lon"] += np.random.normal(0, lon_noise_std, len(noisy))
    if amount_noise_pct > 0:
        noise = np.random.normal(1, amount_noise_pct, len(noisy))
        noisy["amount"] *= np.clip(noise, 0.5, 1.5)

    if device_swap_prob > 0:
        devices = noisy["device_fingerprint"].unique()
        n_swap = int(len(noisy) * device_swap_prob)
        swap_idx = np.random.choice(len(noisy), n_swap, replace=False)
        for idx in swap_idx:
            noisy.at[idx, "device_fingerprint"] = np.random.choice(devices)

    return noisy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-users", type=int, default=500)
    parser.add_argument("--n-txns", type=int, default=5000)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()

    print("Generating clean data...")
    gen = SyntheticUPIGenerator(n_users=args.n_users, n_transactions=args.n_txns, fraud_ratio=0.05)
    df_clean = gen.generate()
    labels = df_clean["is_fraud"].values

    builder = HeterogeneousGraphBuilder()
    builder.build_from_transactions(df_clean, users=gen.users, merchants=gen.merchants, devices=gen.devices)
    builder.add_p2p_edges(df_clean)
    builder.add_device_sharing_edges()
    pyg_data = builder.to_pyg_data()

    device = torch.device("cpu")
    model = PayShieldGNN(hidden_channels=32, num_layers=2).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    x_dict_base = {nt: pyg_data[nt].x.to(device) for nt in pyg_data.node_types}
    edge_index_dict = {et: pyg_data[et].edge_index.to(device) for et in pyg_data.edge_types}

    model.train()
    for epoch in range(20):
        optimizer.zero_grad()
        out = model(x_dict_base, edge_index_dict)
        loss = torch.nn.functional.binary_cross_entropy(
            out, torch.tensor(labels[:len(out)], dtype=torch.float32)
        )
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        clean_pred = model(x_dict_base, edge_index_dict).numpy()
    clean_auc = roc_auc_score(labels[:len(clean_pred)], clean_pred)
    clean_pr = average_precision_score(labels[:len(clean_pred)], clean_pred)

    print(f"\n{'─' * 50}")
    print(f"Sensitivity Analysis")
    print(f"{'─' * 50}")
    print(f"\nClean data: AUC={clean_auc:.4f}, PR-AUC={clean_pr:.4f}")

    experiments = [
        ("Location noise (0.01°)", {"lat_noise_std": 0.01, "lon_noise_std": 0.01}),
        ("Location noise (0.05°)", {"lat_noise_std": 0.05, "lon_noise_std": 0.05}),
        ("Location noise (0.1°)", {"lat_noise_std": 0.1, "lon_noise_std": 0.1}),
        ("Device swap (5%)", {"device_swap_prob": 0.05}),
        ("Device swap (10%)", {"device_swap_prob": 0.10}),
        ("Device swap (20%)", {"device_swap_prob": 0.20}),
        ("Amount noise (5%)", {"amount_noise_pct": 0.05}),
        ("Amount noise (10%)", {"amount_noise_pct": 0.10}),
        ("Amount noise (20%)", {"amount_noise_pct": 0.20}),
    ]

    for name, kwargs in experiments:
        aucs = []
        prs = []
        for t in range(args.trials):
            noisy_df = inject_noise(df_clean, **kwargs)

            builder2 = HeterogeneousGraphBuilder()
            builder2.build_from_transactions(noisy_df, users=gen.users, merchants=gen.merchants, devices=gen.devices)
            builder2.add_p2p_edges(noisy_df)
            builder2.add_device_sharing_edges()
            noisy_data = builder2.to_pyg_data()

            x_dict = {nt: noisy_data[nt].x.to(device) for nt in noisy_data.node_types}
            with torch.no_grad():
                pred = model(x_dict, edge_index_dict).numpy()
            aucs.append(roc_auc_score(labels[:len(pred)], pred))
            prs.append(average_precision_score(labels[:len(pred)], pred))

        auc_drop = (clean_auc - np.mean(aucs)) / clean_auc * 100
        print(f"\n  {name}:")
        print(f"    AUC: {np.mean(aucs):.4f} (±{np.std(aucs):.4f}) [Δ={auc_drop:.1f}%]")
        print(f"    PR-AUC: {np.mean(prs):.4f} (±{np.std(prs):.4f})")

    print(f"{'─' * 50}")


if __name__ == "__main__":
    main()
