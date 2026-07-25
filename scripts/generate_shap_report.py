import argparse
import logging
import os

import torch
from torch_geometric.data import HeteroData

from ml.explainer import (
    DualExplanationMerger,
    ExplanationFormatter,
    GNNExplainerWrapper,
    SHAPBridge,
    SHAPResult,
)
from ml.model import PayShieldGNN

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
    parser = argparse.ArgumentParser(description="Generate SHAP explanation report")
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--output-dir", default="models/explanations")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

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
    data[("user", "performed", "transaction")].edge_index = torch.randint(0, 5, (2, 6)).long()
    data[("transaction", "to", "merchant")].edge_index = torch.randint(0, 3, (2, 4)).long()
    data[("user", "used", "device")].edge_index = torch.randint(0, 2, (2, 3)).long()
    data[("user", "transferred_to", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)
    data[("device", "shared_by", "user")].edge_index = torch.zeros((2, 0), dtype=torch.long)

    tabular_feature_names = [
        "txn_count_1h", "txn_count_24h", "amount_total_1h", "amount_avg_1h",
        "burst_score", "device_multi_device_count", "device_jaccard_similarity",
        "amount_z_score", "combined_anomaly_score",
    ]

    print("Generating graph explanation (GNNExplainer)...")
    explainer = GNNExplainerWrapper(model, epochs=50)
    graph_explanation = explainer.explain(data)
    print(f"  Fidelity: {graph_explanation.fidelity:.4f}")
    print(f"  Pattern: {graph_explanation.fraud_pattern.value}")

    print("\nGenerating tabular explanation (SHAP)...")
    try:
        tabular_tensor = torch.randn(1, len(tabular_feature_names))
        shap_bridge = SHAPBridge(model)
        shap_result = shap_bridge.explain_tabular(tabular_tensor, tabular_feature_names)
        print(f"  Base value: {shap_result.base_value:.4f}")
        print(f"  Top positive: {[f['feature'] for f in shap_result.top_positive_features[:3]]}")
        print(f"  Top negative: {[f['feature'] for f in shap_result.top_negative_features[:3]]}")
    except ImportError as e:
        print(f"  SKIP: {e}")
        shap_result = SHAPResult(feature_names=tabular_feature_names)

    print("\nMerging explanations...")
    merger = DualExplanationMerger()
    unified = merger.merge(graph_explanation, shap_result)
    print(f"\n{unified.combined_summary}")

    report_path = os.path.join(args.output_dir, "explanation_report.txt")
    with open(report_path, "w") as f:
        f.write("=" * 60 + "\n")
        f.write("PayShield Unified Explanation Report\n")
        f.write("=" * 60 + "\n\n")
        f.write(unified.combined_summary)
        f.write("\n\n")
        f.write(ExplanationFormatter.format(graph_explanation))
        if shap_result and shap_result.shap_values:
            f.write(f"\n\nSHAP Tabular Attribution:\n")
            for name, val in zip(shap_result.feature_names, shap_result.shap_values):
                f.write(f"  {name}: {val:.6f}\n")

    print(f"\nReport saved: {report_path}")
    print("Done.")


if __name__ == "__main__":
    main()
