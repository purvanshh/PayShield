import argparse
import logging

from llm.evidence import EvidenceCollector, InvestigationContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def make_mock_l1(decision="ALLOW", rules=None):
    return type("L1Result", (), {
        "decision": decision,
        "triggered_rules": rules or [],
    })()


def make_mock_l2(probability=0.0, graph_features=None):
    return type("L2Result", (), {
        "fraud_probability": probability,
        "source": "L2_GNN",
        "graph_features": graph_features or {},
    })()


def make_mock_ensemble(l1=None, l2=None, decision="ALLOW", confidence=0.0):
    return type("EnsembleResult", (), {
        "decision": decision,
        "confidence": confidence,
        "layer1_result": l1,
        "layer2_result": l2,
    })()


def main():
    parser = argparse.ArgumentParser(description="Test evidence collector")
    parser.add_argument("--txn-id", default="TXN_TEST_001")
    args = parser.parse_args()

    collector = EvidenceCollector(max_evidence_items=10)

    l1 = make_mock_l1("ESCALATE", rules=["V-RULE-03", "G-RULE-02"])
    l2 = make_mock_l2(probability=0.87, graph_features={
        "velocity": {"txn_count_5min": 15, "amount_sum_1h": 250000},
        "geo": {"location_deviation_km": 350},
        "benford": {"chi2": 45.2},
        "shap": {"txn_count": 0.42, "geo_entropy": 0.29, "benford_chi2": 0.18},
        "graph_nodes": [
            {"type": "user", "id": "U10023", "importance": 0.91},
            {"type": "device", "id": "D8841", "importance": 0.87},
        ],
    })

    ensemble = make_mock_ensemble(l1=l1, l2=l2, decision="BLOCK", confidence=0.92)

    ctx = collector.collect(args.txn_id, ensemble)

    print(f"\n{'=' * 60}")
    print(f"INVESTIGATION CONTEXT for {ctx.txn_id}")
    print(f"{'=' * 60}")
    print(f"Decision: {ctx.ensemble_decision}")
    print(f"Confidence: {ctx.ensemble_confidence:.3f}")
    print(f"Timestamp: {ctx.timestamp}")

    print(f"\nEvidence Items ({len(ctx.evidence_items)}):")
    for i, item in enumerate(ctx.evidence_items):
        print(f"  {i + 1}. [{item.type:8s}] [{item.source:8s}] sev={item.severity} imp={item.importance:.2f}")
        print(f"     {item.description[:100]}")

    print(f"\nSHAP Features ({len(ctx.shap_features)}):")
    for feat in ctx.shap_features:
        print(f"  - {feat.name}: {feat.value}")

    print(f"\nGraph Nodes ({len(ctx.graph_nodes)}):")
    for node in ctx.graph_nodes:
        print(f"  - {node.type} {node.id}: {node.importance:.2f}")

    print(f"\nSummary Stats:")
    for k, v in ctx.summary_stats.items():
        print(f"  {k}: {v}")

    print("\nDone.")


if __name__ == "__main__":
    main()
