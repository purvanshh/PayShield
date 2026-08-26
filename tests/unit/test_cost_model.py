"""Cost-model tests: the calculator reproduces docs/COST_MODEL.md exactly.

Review-vs-Block semantics: a wrong flag at the MEDIUM+ review gate costs ₹200
(operator time), not the full order value — only the HIGH/prepaid gate applies
the full false-block penalty.
"""

from docs.cost_model.assumptions import CostAssumptions
from docs.cost_model.calculator import (
    OPERATING_POINTS,
    evaluate_scenario,
    load_scenario,
)


def test_false_allow_and_block_costs():
    a = CostAssumptions()
    assert a.false_allow_cost == 2795.0  # 2500 + 120 + 80 + 45 + 50
    assert a.false_block_cost == 3180.0  # 2500 + 50 + 180 + 0.15*3000
    assert a.review_cost == 200.0


def test_base_scenario_reproduces_doc_headline():
    result = evaluate_scenario(10_000, CostAssumptions(), OPERATING_POINTS["MEDIUM+"])
    assert result["total_returns"] == 1800
    assert result["false_blocks"] == 450
    assert result["true_caught"] == 943
    assert result["prevented"] == 660
    assert result["remaining_returns"] == 1140
    assert result["baseline_cost"] == 5_031_000
    assert result["payshield_cost"] == 3_276_300
    assert result["monthly_savings"] == 1_754_700
    assert round(result["roi_pct"], 1) == 34.9
    # review gate penalises a wrong flag with operator time, not the order
    assert result["flag_penalty_per_order"] == 200.0


def test_high_gate_uses_block_penalty():
    result = evaluate_scenario(10_000, CostAssumptions(), OPERATING_POINTS["HIGH"])
    assert result["flag_penalty_per_order"] == CostAssumptions().false_block_cost
    assert result["false_blocks"] > 0  # precision 0.790, not 1.0
    assert result["monthly_savings"] > 0


def test_scenario_sweep_is_ordered():
    for name in ("fashion", "electronics", "grocery"):
        cfg = load_scenario(name)
        overrides = {k: v for k, v in cfg.items() if k != "description"}
        a = CostAssumptions(**overrides)
        r = evaluate_scenario(10_000, a, OPERATING_POINTS["MEDIUM+"])
        assert r["monthly_savings"] > 0


def test_scenarios_json_is_well_formed():
    for name in ("fashion", "electronics", "grocery"):
        cfg = load_scenario(name)
        assert "aov" in cfg and "return_rate" in cfg
        CostAssumptions(**{k: v for k, v in cfg.items() if k != "description"})
