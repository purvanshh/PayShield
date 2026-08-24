"""Return-risk cost calculator.

Translates the return-risk scorer's precision/recall operating points into
merchant money: monthly savings, annual savings, ROI and the false-block
count per month — for a merchant-sized batch of orders.

The arithmetic mirrors ``docs/COST_MODEL.md`` row-for-row so the numbers a
panelist reads and the numbers the terminal prints are identical:

    caught            = round(recall × total_returns)          # flagged
    wrong_flags       = round(caught × (1 − precision))        # good flagged
    true_caught       = caught − wrong_flags
    prevented         = round(true_caught × diversion_effectiveness)
    remaining_returns = total_returns − prevented

Penalty for a wrong flag depends on the gate's action:
- MEDIUM+ (review)  -> review_cost ₹200 (operator time, not the order value)
- HIGH (block)      -> false_block_cost (full lost order + CAC + churn)

Usage
-----
    python docs/cost_model/calculator.py                 # base scenario
    python docs/cost_model/calculator.py --scenario electronics
    python docs/cost_model/calculator.py --sensitivity   # AOV × return-rate grid
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from docs.cost_model.assumptions import CostAssumptions  # noqa: E402


@dataclass(frozen=True)
class OperatingPoint:
    """A shipped threshold, its measured precision/recall, and the action cost.

    ``action`` distinguishes a REVIEW flag (MEDIUM+ gate: costs operator time,
    never the order value) from a BLOCK/prepaid gate (HIGH: a wrongly flagged
    good order is lost). Measured on the 10k-order calibrated hold-out in
    ``scripts/benchmark_return_risk.py``.
    """

    name: Literal["HIGH", "MEDIUM+", "LOW"]
    threshold: float
    precision: float
    recall: float
    action: Literal["review", "block"] = "review"


OPERATING_POINTS = {
    # Calibrated benchmark (Amazon-margin generator, seed 42, 10k orders):
    # POS rates ~40%, both gates select the same 25% of orders (bimodal score
    # distribution with a gap between 0.50 and 0.70).
    "HIGH": OperatingPoint("HIGH", 0.70, 0.9837, 0.6050, action="block"),
    "MEDIUM+": OperatingPoint("MEDIUM+", 0.50, 0.9837, 0.6050, action="review"),
}


def evaluate_scenario(
    orders: int,
    assumptions: CostAssumptions,
    op: OperatingPoint,
) -> dict[str, Any]:
    """Estimate monthly cost/savings at a given operating point.

    A wrong flag costs ``review_cost`` at the MEDIUM+ review gate but the full
    ``false_block_cost`` at the HIGH/prepaid gate — a corrupted logistics/ops
    model would over-charge every review as a lost order. Every intermediate
    quantity is returned so the story is auditable.
    """
    total_returns = int(orders * assumptions.return_rate)

    caught = int(round(op.recall * total_returns))
    # A flagged order is a wrong flag with probability (1 − precision).
    wrong_flags = int(round(caught * (1.0 - op.precision)))
    true_caught = caught - wrong_flags

    prevented = int(round(true_caught * assumptions.diversion_effectiveness))
    remaining_returns = total_returns - prevented

    wrong_flag_cost = (
        assumptions.review_cost if op.action == "review" else assumptions.false_block_cost
    )

    baseline_cost = total_returns * assumptions.false_allow_cost
    payshield_cost = (
        remaining_returns * assumptions.false_allow_cost
        + wrong_flags * wrong_flag_cost
    )
    savings = baseline_cost - payshield_cost

    return {
        "orders": orders,
        "total_returns": total_returns,
        "caught": caught,
        "false_blocks": wrong_flags,
        "true_caught": true_caught,
        "prevented": prevented,
        "remaining_returns": remaining_returns,
        "baseline_cost": baseline_cost,
        "payshield_cost": payshield_cost,
        "monthly_savings": savings,
        "annual_savings": savings * 12,
        "roi_pct": (savings / baseline_cost) * 100 if baseline_cost else 0.0,
        "cost_per_false_allow": assumptions.false_allow_cost,
        "flag_penalty_per_order": wrong_flag_cost,
        "assumptions": {
            "aov": assumptions.aov,
            "return_rate": assumptions.return_rate,
        },
    }


def load_scenario(scenario: str) -> dict[str, Any]:
    """Load a pre-built merchant scenario from ``scenarios.json``."""
    path = Path(__file__).resolve().parent / "scenarios.json"
    data = json.loads(path.read_text())
    key = scenario if scenario in data else "fashion"
    return data[key]


def _scenario_assumptions(config: dict[str, Any]) -> CostAssumptions:
    overrides = {k: v for k, v in config.items() if k != "description"}
    return CostAssumptions(**overrides)


def _print_header() -> None:
    print("=" * 66)
    print("PAYSHIELD RETURN-RISK COST MODEL")
    print("False-positive vs false-allow costs in Indian e-commerce unit economics")
    print("=" * 66)


def _format_result(result: dict[str, Any], op: OperatingPoint) -> None:
    print(f"\n=== {op.name} Gate (threshold {op.threshold}, action={op.action}) ===")
    print(f"Orders/month            : {result['orders']:,}")
    print(
        f"Expected returns        : {result['total_returns']:,} ({result['assumptions']['return_rate']:.0%})"
    )
    print(f"Flagged (recall)        : {result['caught']:,}")
    print(f"  wrong flags           : {result['false_blocks']:,}")
    print(f"  true catches          : {result['true_caught']:,}")
    print(f"Returns prevented       : {result['prevented']:,} (diversion @ 70%)")
    print(f"Remaining returns       : {result['remaining_returns']:,}")
    print("-" * 66)
    print(f"Cost per false allow    : ₹{result['cost_per_false_allow']:,.0f}")
    print(f"Wrong-flag penalty      : ₹{result['flag_penalty_per_order']:,.0f} "
          f"({'review' if op.action == 'review' else 'block'})")
    print("Baseline (no model)      : ₹{:,}".format(result["baseline_cost"]))
    print("With PayShield           : ₹{:,}".format(result["payshield_cost"]))
    print(f"MONTHLY SAVINGS          : ₹{result['monthly_savings']:,.0f}")
    print(f"ANNUAL SAVINGS           : ₹{result['annual_savings']:,.0f}")
    print(f"ROI                      : {result['roi_pct']:.1f}%")


def _run_scenario(scenario: str, orders: int, op_name: str) -> None:
    config = load_scenario(scenario)
    assumptions = _scenario_assumptions(config)
    op = OPERATING_POINTS[op_name]
    _print_header()
    print(f"\nScenario : {scenario} ({config.get('description', '')})")
    result = evaluate_scenario(orders, assumptions, op)
    _format_result(result, op)


def _run_sensitivity(orders: int, op_name: str) -> None:
    base = CostAssumptions()
    op = OPERATING_POINTS[op_name]
    _print_header()
    print("\nSensitivity: monthly savings across AOV × return-rate (MEDIUM+ gate)")
    print(
        f"{'AOV':>7} | {'Return rate':>11} | {'Monthly savings':>16} | {'Annual savings':>15} | {'ROI':>6}"
    )
    print("-" * 68)
    for aov, rate in ((1500, 0.12), (2500, 0.18), (4000, 0.25)):
        a = CostAssumptions(
            aov=aov,
            return_rate=rate,
            return_logistics=base.return_logistics,
            restocking=base.restocking,
            service_cost=base.service_cost,
            gateway_fee_pct=base.gateway_fee_pct,
            cac=base.cac,
            churn_after_false_block=base.churn_after_false_block,
            ltv=base.ltv,
            diversion_effectiveness=base.diversion_effectiveness,
        )
        r = evaluate_scenario(orders, a, op)
        print(
            f"{aov:>7,} | {rate:>10.0%} | "
            f"₹{r['monthly_savings']:>14,} | ₹{r['annual_savings']:>13,} | {r['roi_pct']:>5.1f}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Return-risk cost model calculator")
    parser.add_argument("--orders", type=int, default=10_000, help="orders per month")
    parser.add_argument("--scenario", default="fashion", help="fashion | electronics | grocery")
    parser.add_argument("--operating-point", default="MEDIUM+", help="HIGH | MEDIUM+")
    parser.add_argument("--sensitivity", action="store_true", help="AOV × return-rate grid")
    args = parser.parse_args()

    op_name = args.operating_point.upper()
    if op_name not in OPERATING_POINTS:
        sys.exit(f"unknown operating point: {args.operating_point}")

    if args.sensitivity:
        _run_sensitivity(args.orders, op_name)
    else:
        _run_scenario(args.scenario.lower(), args.orders, op_name)


if __name__ == "__main__":
    main()
