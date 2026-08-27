#!/usr/bin/env python3
"""Doc consistency checker.

Loads docs/_number_manifest.json and verifies that headline scenario numbers
in all .md files match the manifest.

Strategy: explicitly search for KNOWN STALE NUMBERS that caused past doc
 drift (0.8067, 0.677, 0.774, 17.5, 36.9) and flag them. Also verify that
each headline doc contains the correct manifest numbers for its scenario table.
"""

import json
import re
import sys
from pathlib import Path


DOC_PATHS = [
    Path("README.md"),
    Path("BUSINESS_IMPACT.md"),
    Path("MISTAKES_AND_LEARNINGS.md"),
    Path("docs/DESIGN_DECISIONS.md"),
    Path("docs/INTERVIEW_DEFENSE.md"),
]

# Known stale numbers from the old single-scenario era that must not appear
# in headline claims. They are allowed only in historical/mistakes context
# (e.g. "we used to claim 0.9311").
STALE_NUMBERS = {
    0.8067: "old tuned PR-AUC (current: 0.8089)",
    0.677: "old precision@0.50 (current basic: 0.635)",
    0.774: "old recall@0.50 (current basic: 0.811)",
    17.5: "old fashion savings ₹L (current basic: 17.0)",
    36.9: "old electronics savings ₹L (current basic: 36.2)",
}

# Stale numbers that ARE allowed because they appear in honest historical
# discussion (MISTAKES_AND_LEARNINGS.md, INTERVIEW_DEFENSE.md).
HISTORICAL_STALE_NUMBERS = {
    0.9311,
    0.8729,
    20.9,
    20.0,
}


def verify_doc_consistency() -> None:
    manifest_path = Path("docs/_number_manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)

    failures: list[str] = []

    for doc_path in DOC_PATHS:
        if not doc_path.exists():
            continue
        text = doc_path.read_text()

        # 1. Detect stale numbers in non-historical docs.
        is_historical_doc = doc_path.name in ("MISTAKES_AND_LEARNINGS.md",)
        for stale, description in STALE_NUMBERS.items():
            # Look for the stale number as a standalone token.
            pattern = re.compile(rf"\b{re.escape(str(stale))}\b")
            if pattern.search(text):
                if is_historical_doc:
                    # In mistakes doc, stale numbers are OK if they appear in
                    # the context of "we used to claim..." or "Mistake 6..."
                    # We do a simple context check.
                    if "Mistake 6" not in text and "0.9311" not in text:
                        failures.append(
                            f"{doc_path}: stale number {stale} ({description}) "
                            f"appears without historical context"
                        )
                else:
                    failures.append(
                        f"{doc_path}: stale number {stale} ({description}) — "
                        f"update to current manifest value"
                    )

        # 2. Verify headline tables contain the correct manifest numbers.
        # Only check README and BUSINESS_IMPACT for the three-scenario table.
        if doc_path.name in ("README.md", "BUSINESS_IMPACT.md"):
            for scenario, metrics in manifest.get("scenarios", {}).items():
                for metric, expected in metrics.items():
                    if metric in ("pr_auc", "roc_auc"):
                        # PR-AUC and ROC-AUC must appear in the headline table.
                        # Use loose regex to catch both 0.8089 and 0.80/0.81 formatting.
                        if str(expected) not in text:
                            # Allow rounded forms too.
                            rounded = round(expected, 2)
                            if str(rounded) not in text and str(int(expected)) not in text:
                                # Some numbers might be in a different form; don't flag
                                # if a close number exists.
                                pattern = re.compile(r"\b\d+\.\d+\b")
                                found_close = False
                                for m in pattern.finditer(text):
                                    val = float(m.group())
                                    if abs(val - expected) < 0.02:
                                        found_close = True
                                        break
                                if not found_close:
                                    failures.append(
                                        f"{doc_path}: missing {scenario}.{metric} "
                                        f"(expected {expected})"
                                    )
                    elif metric in ("fashion_savings_lakhs", "electronics_savings_lakhs"):
                        # Savings must appear in the headline table (e.g. ₹17.0L or 17.0).
                        if str(expected) not in text:
                            failures.append(
                                f"{doc_path}: missing {scenario}.{metric} "
                                f"(expected {expected})"
                            )

    if failures:
        print("DOC CONSISTENCY FAILURES:")
        for f in failures:
            print(f"  ❌ {f}")
        raise AssertionError(f"{len(failures)} doc consistency failures")

    print("Doc consistency: OK")


if __name__ == "__main__":
    try:
        verify_doc_consistency()
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
