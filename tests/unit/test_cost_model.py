"""Cost-model tests: the calculator reproduces the measured headline numbers.

Review-vs-Block semantics: a wrong flag at the MEDIUM+ review gate costs ₹200
(operator time), not the full order value — only the HIGH/prepaid gate applies
the full false-block penalty.

The MEDIUM+ operating point is loaded from the measured basic-scenario results
(``models/return_risk_results_basic.json``) — no hardcoded P/R constants in
production code (that caused Mistake 6). The HIGH gate test constructs a fixed
``OperatingPoint`` fixture to exercise the block-cost path; those P/R values are
test inputs, not production constants.
"""

from docs.cost_model.assumptions import CostAssumptions
from docs.cost_model.calculator import (
    OperatingPoint,
    evaluate_scenario,
    load_maturity_operating_point,
    load_scenario,
)


def test_false_allow_and_block_costs():
    a = CostAssumptions()
    assert a.false_allow_cost == 2795.0  # 2500 + 120 + 80 + 45 + 50
    assert a.false_block_cost == 3180.0  # 2500 + 50 + 180 + 0.15*3000
    assert a.review_cost == 200.0


def test_base_scenario_reproduces_measured_headline():
    # MEDIUM+ point loaded from the measured basic results JSON (no hardcoded fallback).
    op, _curve = load_maturity_operating_point("basic", gate=0.50)
    result = evaluate_scenario(10_000, CostAssumptions(), op)
    assert op.action == "review"
    assert result["total_returns"] == 1800
    # Measured default basic model (canonical stack): P 0.644, R 0.812 -> caught 1461, false_flags 520.
    assert result["caught"] == 1461
    assert result["false_blocks"] == 520
    assert result["true_caught"] == 941
    assert result["prevented"] == 659
    assert result["remaining_returns"] == 1141
    assert result["baseline_cost"] == 5_031_000
    assert result["payshield_cost"] == 3_293_095
    assert result["monthly_savings"] == 1_737_905  # ₹17.4L
    assert round(result["roi_pct"], 1) == 34.5
    # review gate penalises a wrong flag with operator time, not the order
    assert result["flag_penalty_per_order"] == 200.0


def test_high_gate_uses_block_penalty():
    # Fixed fixture exercising the BLOCK cost path (P/R are test inputs).
    op = OperatingPoint("HIGH", 0.70, 0.790, 0.595, action="block")
    result = evaluate_scenario(10_000, CostAssumptions(), op)
    assert result["flag_penalty_per_order"] == CostAssumptions().false_block_cost
    assert result["false_blocks"] > 0  # precision 0.790, not 1.0
    assert result["monthly_savings"] > 0


def test_scenario_sweep_is_ordered():
    op, _curve = load_maturity_operating_point("basic", gate=0.50)
    for name in ("fashion", "electronics", "grocery"):
        cfg = load_scenario(name)
        overrides = {k: v for k, v in cfg.items() if k != "description"}
        a = CostAssumptions(**overrides)
        r = evaluate_scenario(10_000, a, op)
        assert r["monthly_savings"] > 0


def test_scenarios_json_is_well_formed():
    for name in ("fashion", "electronics", "grocery"):
        cfg = load_scenario(name)
        assert "aov" in cfg and "return_rate" in cfg
        CostAssumptions(**{k: v for k, v in cfg.items() if k != "description"})
