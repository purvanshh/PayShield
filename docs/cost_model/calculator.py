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
    # Offline XGBoost operating points, measured on the seed-42 2,000-order
    # held-out test set (scripts/train_xgb_return_risk.py, PR-AUC 0.8067 on
    # the returned label). The enriched feature pipeline exists in the
    # codebase but the XGBoost model has not been recalibrated to enriched
    # distributions — see MISTAKES_AND_LEARNINGS.md (Mistake 6).
    "HIGH": OperatingPoint("HIGH", 0.70, 0.790, 0.595, action="block"),
    "MEDIUM+": OperatingPoint("MEDIUM+", 0.50, 0.677, 0.774, action="review"),
}

# Operating curve of the tuned XGBoost model: {gate: (flag_rate, recall)}.
# Measured on the seed-42 2,000-order hold-out of
# scripts/train_xgb_return_risk.py (models/return_risk_xgb_best.json). Used by
# vertical_sensitivity() to project precision at any base rate via
# precision(gate, b) = recall(gate) * b / flag_rate(gate).
_XGB_OPERATING_CURVE = {
    0.20: (0.7665, 0.9545),
    0.25: (0.6995, 0.9242),
    0.30: (0.6385, 0.9015),
    0.35: (0.5855, 0.8737),
    0.40: (0.5345, 0.8409),
    0.45: (0.4920, 0.8081),
    0.50: (0.4530, 0.7740),
    0.60: (0.3805, 0.7008),
    0.70: (0.2980, 0.5947),
}


def vertical_sensitivity(
    orders: int = 10_000,
    gates: list[float] | None = None,
    verticals: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Sweep the review gate across merchant verticals of different base rates.

    At a fixed gate, precision scales with the base rate (fewer real returns
    among the flagged tail), while recall and the flag rate stay fixed. So
    ``precision(gate, b) = recall(gate) * b / flag_rate(gate)`` using the tuned
    model's measured operating curve. The review gate (₹200/flag) is the only
    action considered - blocking (₹3,180) is a separate, stricter surface.

    Prints a markdown table and writes ``vertical_sensitivity.json``.
    """
    assumptions = CostAssumptions()  # ₹2,500 AOV, ₹200 review cost, 10k orders
    gates = gates or [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70]
    verticals = verticals or [
        ("Fashion (high return)", 0.32),
        ("Fashion (low return)", 0.14),
        ("Electronics", 0.08),
        ("Grocery", 0.04),
    ]

    rows = []
    for label, base_rate in verticals:
        best: tuple[float, float, dict] | None = None  # (savings, gate, result)
        at_050: dict[str, Any] | None = None
        for gate in gates:
            if gate not in _XGB_OPERATING_CURVE:
                continue
            flag_rate, recall = _XGB_OPERATING_CURVE[gate]
            precision = min(1.0, recall * base_rate / max(flag_rate, 1e-9))
            op = OperatingPoint("MEDIUM+", gate, precision, recall, action="review")
            assumptions = CostAssumptions(return_rate=base_rate)
            res = evaluate_scenario(orders, assumptions, op)
            if abs(gate - 0.50) < 1e-9:
                at_050 = res
            if best is None or res["monthly_savings"] > best[0]:
                best = (res["monthly_savings"], gate, res)

        assert best is not None and at_050 is not None
        best_savings, best_gate, best_res = best
        rows.append(
            {
                "vertical": label,
                "base_return_rate": base_rate,
                "optimal_gate": best_gate,
                "net_050": at_050["monthly_savings"],
                "net_optimal": best_res["monthly_savings"],
                "roi_050_pct": at_050["roi_pct"],
                "roi_optimal_pct": best_res["roi_pct"],
                "precision_optimal": best_res["caught"] and (best_res["true_caught"] / best_res["caught"]) or 0.0,
                "recall_optimal": best_res["caught"] / best_res["total_returns"] if best_res["total_returns"] else 0.0,
            }
        )

    _print_sensitivity_markdown(rows)

    out = {
        "method": "precision(gate, b) = recall(gate) * b / flag_rate(gate) on the tuned XGBoost operating curve",
        "orders": orders,
        "assumptions": {
            "aov": assumptions.aov,
            "review_cost": assumptions.review_cost,
            "diversion_effectiveness": assumptions.diversion_effectiveness,
        },
        "note": "Synthetic projections. Real merchant data would calibrate the base rate and gate jointly.",
        "verticals": rows,
    }
    path = Path(__file__).resolve().parent / "vertical_sensitivity.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {path}")
    return out


def _print_sensitivity_markdown(rows: list[dict[str, Any]]) -> None:
    def fmt_rupees(v: float) -> str:
        cr = v / 10_000_000
        if abs(cr) >= 1:
            return f"{cr:+.2f} cr"
        return f"₹{v/100_000:+.1f}L"

    print("=" * 80)
    print("VERTICAL SENSITIVITY — net savings vs base return rate (10k orders, review gate ₹200)")
    print("=" * 80)
    print("| Merchant vertical | Base return rate | Optimal gate | Net ₹/month at 0.50 gate | Net ₹/month at optimal gate |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['vertical']} | {r['base_return_rate']:.0%} | {r['optimal_gate']:.2f} | "
            f"{fmt_rupees(r['net_050'])} | {fmt_rupees(r['net_optimal'])} |"
        )
    print(
        "\nAt low base rates, a 0.50 gate flags ~45% of orders while too few are real "
        "returns to cover review costs. The gate is only optimal for high-return verticals."
    )


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


def _build_json_report(orders: int, op_name: str, path: Path) -> None:
    """Write the cost model's authoritative result set to ``path``.

    Consumed by the dashboard via ``GET /v1/meta/return-risk/cost`` so the UI
    always renders what the calculator measures — no duplicated TS constants.
    """
    from datetime import UTC, datetime

    op = OPERATING_POINTS[op_name]

    scenarios = []
    for key in ("fashion", "electronics", "grocery"):
        config = load_scenario(key)
        assumptions = _scenario_assumptions(config)
        r = evaluate_scenario(orders, assumptions, op)
        scenarios.append(
            {
                "key": key,
                "label": key.title(),
                "description": config.get("description", ""),
                "aov": assumptions.aov,
                "return_rate": assumptions.return_rate,
                "monthly_savings": r["monthly_savings"],
                "annual_savings": r["annual_savings"],
                "roi_pct": r["roi_pct"],
                "prevented": r["prevented"],
                "wrong_flags": r["false_blocks"],
                "baseline_cost": r["baseline_cost"],
                "payshield_cost": r["payshield_cost"],
                "false_allow_cost": r["cost_per_false_allow"],
            }
        )

    base = CostAssumptions()
    sensitivity = []
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
        sensitivity.append(
            {
                "aov": aov,
                "return_rate": rate,
                "monthly_savings": r["monthly_savings"],
                "annual_savings": r["annual_savings"],
                "roi_pct": r["roi_pct"],
            }
        )

    report = {
        "operating_point": {
            "name": op.name,
            "threshold": op.threshold,
            "precision": op.precision,
            "recall": op.recall,
            "action": op.action,
            "wrong_flag_cost": base.review_cost,
        },
        "scenarios": scenarios,
        "sensitivity": sensitivity,
        "orders": orders,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Return-risk cost model calculator")
    parser.add_argument("--orders", type=int, default=10_000, help="orders per month")
    parser.add_argument("--scenario", default="fashion", help="fashion | electronics | grocery")
    parser.add_argument("--operating-point", default="MEDIUM+", help="HIGH | MEDIUM+")
    parser.add_argument("--sensitivity", action="store_true", help="AOV × return-rate grid")
    parser.add_argument(
        "--vertical-sensitivity",
        action="store_true",
        help="gate sweep across vertical base rates (writes docs/cost_model/vertical_sensitivity.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write models/cost_model_results.json and exit (consumed by the dashboard)",
    )
    args = parser.parse_args()

    op_name = args.operating_point.upper()
    if op_name not in OPERATING_POINTS:
        sys.exit(f"unknown operating point: {args.operating_point}")

    if args.vertical_sensitivity:
        vertical_sensitivity(orders=args.orders)
        return

    if args.json:
        _build_json_report(args.orders, op_name, Path("models/cost_model_results.json"))
        print("wrote models/cost_model_results.json")
        return

    if args.sensitivity:
        _run_sensitivity(args.orders, op_name)
    else:
        _run_scenario(args.scenario.lower(), args.orders, op_name)


if __name__ == "__main__":
    main()
