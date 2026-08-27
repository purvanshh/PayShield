#!/usr/bin/env python3
"""Dashboard compatibility smoke test.

Verifies that models/cost_model_results.json contains both the legacy
'scenarios' key (consumed by the dashboard CostModelPage) and the new
'maturity_scenarios' key.
"""

import json
import sys
from pathlib import Path


def verify_dashboard_compat() -> None:
    path = Path("models/cost_model_results.json")
    if not path.exists():
        raise FileNotFoundError(f"Dashboard compat broken: {path} not found")

    with open(path) as f:
        data = json.load(f)

    assert "scenarios" in data, "Dashboard compat broken: missing legacy 'scenarios' key"
    assert "maturity_scenarios" in data, "Missing new 'maturity_scenarios' key"
    print("Dashboard compat: OK")


if __name__ == "__main__":
    try:
        verify_dashboard_compat()
    except (AssertionError, FileNotFoundError) as e:
        print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
