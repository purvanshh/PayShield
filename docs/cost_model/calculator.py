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


# Operating curve of the basic-scenario XGBoost model, measured on the
# seed-42 2,000-order hold-out and emitted to
# models/return_risk_results_basic.json by scripts/train_xgb_return_risk.py.
# Used by vertical_sensitivity() to project precision at any base rate via
# precision(gate, b) = recall(gate) * b / flag_rate(gate).
#
# NO HARDCODED CONSTANT — the curve is loaded from the measured JSON so the ₹
# figures always track the actual model. Using stale constants caused Mistake 6
# (₹20.9L attribution error). See MISTAKES_AND_LEARNINGS.md.
def _load_basic_curve() -> dict[float, tuple[float, float]]:
    """Return ``{gate: (flag_rate, recall)}`` from the basic results JSON.

    Hard-fails if the JSON is missing — no fallback to stale constants.
    """
    path = Path("models") / "return_risk_results_basic.json"
    with open(path) as f:
        data = json.load(f)
    curve = data.get("operating_curve", {})
    out: dict[float, tuple[float, float]] = {}
    for gate_str, pt in curve.items():
        out[float(gate_str)] = (pt["flag_rate"], pt["recall"])
    return out


def vertical_sensitivity(
    orders: int = 10_000,
    gates: list[float] | None = None,
    verticals: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Sweep the review gate across merchant verticals of different base rates.

    At a fixed gate, precision scales with the base rate (fewer real returns
    among the flagged tail), while recall and the flag rate stay fixed. So
    ``precision(gate, b) = recall(gate) * b / flag_rate(gate)`` using the basic
    model's *measured* operating curve (loaded from JSON, never a stale
    constant). The review gate (₹200/flag) is the only action considered -
    blocking (₹3,180) is a separate, stricter surface.

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

    # Measured curve from the basic results JSON (no hardcoded fallback).
    curve = _load_basic_curve()

    rows = []
    for label, base_rate in verticals:
        best: tuple[float, float, dict] | None = None  # (savings, gate, result)
        at_050: dict[str, Any] | None = None
        for gate in gates:
            if gate not in curve:
                continue
            flag_rate, recall = curve[gate]
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


def _load_basic_operating_point(gate: float = 0.50) -> OperatingPoint:
    """Load the basic-scenario operating point from the measured JSON.

    NO FALLBACK — the legacy vertical-only path must use measured numbers,
    not the stale hardcoded constants that caused Mistake 6.
    """
    op, _curve = load_maturity_operating_point("basic", gate=gate)
    return op


def _run_scenario(scenario: str, orders: int, op_name: str) -> None:
    config = load_scenario(scenario)
    assumptions = _scenario_assumptions(config)
    # Legacy path: load measured P/R from basic results JSON.
    # NO FALLBACK — using stale constants caused Mistake 6.
    op = _load_basic_operating_point(gate=0.50)
    _print_header()
    print(f"\nScenario : {scenario} ({config.get('description', '')})")
    result = evaluate_scenario(orders, assumptions, op)
    _format_result(result, op)


def _run_sensitivity(orders: int, op_name: str) -> None:
    base = CostAssumptions()
    # Legacy path: load measured P/R from basic results JSON.
    # NO FALLBACK — using stale constants caused Mistake 6.
    op = _load_basic_operating_point(gate=0.50)
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


def _build_json_report(orders: int, path: Path) -> None:
    """Write the cost model's authoritative result set to ``path``.

    Consumed by the dashboard via ``GET /v1/meta/return-risk/cost`` so the UI
    always renders what the calculator measures — no duplicated TS constants.
    """
    from datetime import UTC, datetime

    # Legacy path: load measured P/R from basic results JSON.
    # NO FALLBACK — using stale constants caused Mistake 6.
    op = _load_basic_operating_point(gate=0.50)

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


# --------------------------------------------------------------------------- #
# Progressive Merchant Maturity scenarios (basic | enriched | premium)
# --------------------------------------------------------------------------- #
# Each maturity stage ships a measured operating curve in
# models/return_risk_results_{maturity}.json (written by train_xgb_return_risk).
# The calculator loads the *measured* precision/recall at the 0.50 gate instead
# of stale hardcoded constants, so the ₹ figures track the actual model. NO
# FALLBACK — using stale constants caused Mistake 6 (₹20.9L attribution error).
# The headline method is unchanged: measured P/R@0.50 applied to each vertical's
# assumed return rate (the same way the existing ₹17.4L is derived).

MATURITY_STAGES = ("basic", "enriched", "premium")


def load_maturity_operating_point(maturity: str, gate: float = 0.50) -> tuple[OperatingPoint, dict]:
    """Read the measured operating curve + 0.50-gate P/R for one maturity stage.

    Returns the OperatingPoint (MEDIUM+, review action) and the full curve dict
    ``{gate: {flag_rate, precision, recall}}``.

    NO FALLBACK — using stale constants caused Mistake 6 (₹20.9L attribution
    error). If the per-stage results file is missing, the script crashes.
    """
    # Load measured P/R from the training script output.
    # NO FALLBACK — using stale constants caused Mistake 6 (see MISTAKES_AND_LEARNINGS.md).
    path = Path("models") / f"return_risk_results_{maturity}.json"
    with open(path) as f:
        data = json.load(f)
    curve = data.get("operating_curve", {})
    key = f"{gate:.2f}"
    if key not in curve:
        raise KeyError(f"Gate {key} not found in operating curve for {maturity}")
    pt = curve[key]
    op = OperatingPoint("MEDIUM+", gate, pt["precision"], pt["recall"], action="review")
    return op, curve


def compute_maturity_table(orders: int = 10_000) -> dict[str, Any]:
    """Unified 3-stage x 2-vertical table (Fashion + Electronics) with measured
    PR-AUC / ROC-AUC / P@0.50 / R@0.50 / Net ₹/month / ROI.

    Fashion = ₹2.5k AOV, 18% return; Electronics = ₹8k AOV, 12% return (the
    existing scenarios.json values - Electronics' ₹8k AOV is what already yields
    ₹36.9L at the basic operating point and >₹36.9L at premium).
    """
    verticals = [
        ("fashion", load_scenario("fashion")),
        ("electronics", load_scenario("electronics")),
    ]
    rows = []
    for maturity in MATURITY_STAGES:
        op, _curve = load_maturity_operating_point(maturity)
        # Pull the headline metrics from the results file for the table.
        rpath = Path("models") / f"return_risk_results_{maturity}.json"
        pr_auc = roc_auc = None
        if rpath.exists():
            models = json.loads(rpath.read_text()).get("models", [])
            for m in models:
                if m.get("name") == "XGBoost (default)":
                    pr_auc = m.get("pr_auc")
                    roc_auc = m.get("roc_auc")
                    break
        for vkey, vcfg in verticals:
            assumptions = _scenario_assumptions(vcfg)
            res = evaluate_scenario(orders, assumptions, op)
            rows.append(
                {
                    "maturity": maturity,
                    "vertical": vkey,
                    "aov": assumptions.aov,
                    "return_rate": assumptions.return_rate,
                    "pr_auc": pr_auc,
                    "roc_auc": roc_auc,
                    "precision_at_050": op.precision,
                    "recall_at_050": op.recall,
                    "monthly_savings": res["monthly_savings"],
                    "annual_savings": res["annual_savings"],
                    "roi_pct": res["roi_pct"],
                }
            )

    _print_maturity_table(rows)
    return {"orders": orders, "rows": rows}


def _fmt_rupees(v: float) -> str:
    cr = v / 10_000_000
    if abs(cr) >= 1:
        return f"{cr:+.2f} cr"
    return f"₹{v / 100_000:+.2f}L"


def _print_maturity_table(rows: list[dict[str, Any]]) -> None:
    print("=" * 96)
    print("PROGRESSIVE MERCHANT MATURITY — measured model × merchant vertical (10k orders, 0.50 review gate)")
    print("=" * 96)
    print(f"{'Scenario':<10}{'Vertical':<13}{'PR-AUC':>8}{'ROC-AUC':>9}{'P@0.50':>8}{'R@0.50':>8}{'Net ₹/month':>15}{'ROI':>9}")
    print("-" * 96)
    for r in rows:
        pr = f"{r['pr_auc']:.4f}" if r["pr_auc"] is not None else "n/a"
        roc = f"{r['roc_auc']:.4f}" if r["roc_auc"] is not None else "n/a"
        print(
            f"{r['maturity']:<10}{r['vertical']:<13}{pr:>8}{roc:>9}"
            f"{r['precision_at_050']:>8.3f}{r['recall_at_050']:>8.3f}"
            f"{_fmt_rupees(r['monthly_savings']):>15}{r['roi_pct']:>8.1f}%"
        )
    print(
        "\nStage 1 (basic) is the honest floor (PR-AUC ~0.80). Each stage adds observed features + "
        "lower unobserved variance;\nthe ₹ figures rise because the measured precision/recall at the "
        "0.50 gate improve — not because the base rate or AOV changed."
    )


def _write_maturity_cost_report(orders: int, path: Path, table: dict[str, Any] | None = None) -> None:
    """Append the maturity scenarios to models/cost_model_results.json (the
    legacy ``scenarios`` key is preserved for backward dashboard compat)."""
    from datetime import UTC, datetime

    if table is None:
        table = compute_maturity_table(orders)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing["maturity_scenarios"] = {
        "orders": orders,
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": table["rows"],
        "note": "Per-stage measured P/R@0.50 (from models/return_risk_results_{maturity}.json) applied to each vertical.",
    }
    path.write_text(json.dumps(existing, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Return-risk cost model calculator")
    parser.add_argument("--orders", type=int, default=10_000, help="orders per month")
    parser.add_argument("--scenario", default="fashion", help="fashion | electronics | grocery (merchant vertical)")
    parser.add_argument(
        "--maturity",
        choices=MATURITY_STAGES,
        default=None,
        help="basic | enriched | premium (merchant maturity stage) — uses the stage's measured P/R",
    )
    parser.add_argument("--all-maturity", action="store_true", help="print the unified 3-stage × 2-vertical table")
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

    if args.all_maturity:
        table = compute_maturity_table(args.orders)
        _write_maturity_cost_report(args.orders, Path("models/cost_model_results.json"), table=table)
        print("\nwrote models/cost_model_results.json (maturity_scenarios added; legacy scenarios key preserved)")
        return

    if args.maturity:
        op, _curve = load_maturity_operating_point(args.maturity)
        config = load_scenario(args.scenario)
        assumptions = _scenario_assumptions(config)
        _print_header()
        print(f"\nMaturity stage : {args.maturity}  |  Vertical : {args.scenario}")
        print(f"Measured P/R @0.50 : P={op.precision:.3f}  R={op.recall:.3f}")
        res = evaluate_scenario(args.orders, assumptions, op)
        _format_result(res, op)
        return

    if args.vertical_sensitivity:
        vertical_sensitivity(orders=args.orders)
        return

    if args.json:
        _build_json_report(args.orders, Path("models/cost_model_results.json"))
        print("wrote models/cost_model_results.json")
        return

    if args.sensitivity:
        _run_sensitivity(args.orders, "MEDIUM+")
    else:
        _run_scenario(args.scenario.lower(), args.orders, "MEDIUM+")


if __name__ == "__main__":
    main()
