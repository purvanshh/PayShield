import argparse
import json
import logging
from datetime import datetime

from llm.evidence import EvidenceCollector, InvestigationContext
from llm.parser import FallbackGenerator, NarrativeParser

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


SAMPLE_RAW_OUTPUTS = [
    {
        "name": "valid_mule_ring",
        "output": json.dumps({
            "narrative": (
                "User U10023 exhibits classic mule behavior: 15 near-threshold "
                "transactions in 5 minutes from a device shared with 11 other "
                "accounts. Graph analysis confirms second-degree connections to "
                "8 flagged accounts, indicating coordinated mule ring activity."
            ),
            "fraud_type": "MULE_RING",
            "confidence": "HIGH",
            "recommended_action": "BLOCK",
            "key_evidence": [
                "15 transactions in 5 minutes",
                "Shared device across 12 users",
            ],
            "reasoning": (
                "Velocity spike, device sharing, and proximity to known bad "
                "actors collectively indicate a coordinated mule operation."
            ),
        }),
    },
    {
        "name": "valid_burst_attack",
        "output": json.dumps({
            "narrative": (
                "Merchant M3301 under active burst attack: 47 transactions "
                "from 23 cities in 3 minutes — a 40x spike over normal velocity."
            ),
            "fraud_type": "BURST_ATTACK",
            "confidence": "HIGH",
            "recommended_action": "BLOCK",
            "key_evidence": [
                "47 transactions in 3 minutes",
                "23 distinct cities in 180 seconds",
            ],
            "reasoning": (
                "Massive velocity spike combined with impossible geographic "
                "distribution indicates automated scripted attack."
            ),
        }),
    },
    {
        "name": "malformed_missing_fields",
        "output": 'Some text before {\n  "narrative": "Short note",\n  "fraud_type": "INVALID_TYPE"\n} some text after',
    },
    {
        "name": "malformed_not_json",
        "output": "The transaction looks suspicious based on velocity. I recommend blocking this user.",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Validate narrative parser")
    parser.add_argument("--txn-id", default="TXN_VAL_001")
    args = parser.parse_args()

    narrative_parser = NarrativeParser()
    fallback = FallbackGenerator()

    collector = EvidenceCollector()

    l1 = type("L1Result", (), {
        "decision": "ESCALATE",
        "triggered_rules": ["V-RULE-03"],
    })()
    l2 = type("L2Result", (), {
        "fraud_probability": 0.87,
        "source": "L2_GNN",
        "graph_features": {
            "velocity": {"txn_count_5min": 15, "amount_sum_1h": 250000},
            "geo": {"location_deviation_km": 350},
            "benford": {"chi2": 45.2},
        },
    })()
    ensemble = type("EnsembleResult", (), {
        "decision": "BLOCK",
        "confidence": 0.92,
        "layer1_result": l1,
        "layer2_result": l2,
    })()

    ctx = collector.collect(args.txn_id, ensemble)

    print(f"\n{'=' * 60}")
    print("NARRATIVE PARSER TESTS")
    print(f"{'=' * 60}")

    for sample in SAMPLE_RAW_OUTPUTS:
        print(f"\n--- Test: {sample['name']} ---")
        report = narrative_parser.parse(
            sample["output"], txn_id=args.txn_id, expected_action="BLOCK"
        )
        print(f"  Narrative: {report.narrative[:80]}...")
        print(f"  Fraud type: {report.fraud_type}")
        print(f"  Confidence: {report.confidence}")
        print(f"  Action: {report.recommended_action}")
        print(f"  Quality: {report.quality_score:.3f}")
        print(f"  Evidence: {report.key_evidence[:2]}")

    print(f"\n{'=' * 60}")
    print("FALLBACK GENERATOR TEST")
    print(f"{'=' * 60}")
    fb_report = fallback.generate(ctx)
    print(f"  Narrative: {fb_report.narrative[:100]}...")
    print(f"  Fraud type: {fb_report.fraud_type}")
    print(f"  Confidence: {fb_report.confidence}")
    print(f"  Action: {fb_report.recommended_action}")
    print(f"  Quality: {fb_report.quality_score:.3f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
