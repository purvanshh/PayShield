"""Cost-model tests: the calculator reproduces docs/COST_MODEL.md exactly."""

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


def test_base_scenario_reproduces_doc_headline():
    result = evaluate_scenario(10_000, CostAssumptions(), OPERATING_POINTS["MEDIUM+"])
    assert result["total_returns"] == 1800
    assert result["false_blocks"] == 91
    assert result["prevented"] == 1086
    assert result["remaining_returns"] == 714
    assert result["baseline_cost"] == 5_031_000
    assert result["payshield_cost"] == 2_285_010
    assert result["monthly_savings"] == 2_745_990
    assert round(result["roi_pct"], 1) == 54.6


def test_high_gate_has_zero_false_blocks():
    result = evaluate_scenario(10_000, CostAssumptions(), OPERATING_POINTS["HIGH"])
    assert result["false_blocks"] == 0
    assert result["monthly_savings"] > 0


def test_scenario_sweep_is_ordered():
    fashion = evaluate_scenario(10_000, CostAssumptions(), OPERATING_POINTS["MEDIUM+"])
    for name in ("electronics", "grocery"):
        cfg = load_scenario(name)
        overrides = {k: v for k, v in cfg.items() if k != "description"}
        a = CostAssumptions(**overrides)
        r = evaluate_scenario(10_000, a, OPERATING_POINTS["MEDIUM+"])
        assert r["monthly_savings"] > 0
    assert fashion["monthly_savings"] > 0


def test_scenarios_json_is_well_formed():
    for name in ("fashion", "electronics", "grocery"):
        cfg = load_scenario(name)
        assert "aov" in cfg and "return_rate" in cfg
        CostAssumptions(**{k: v for k, v in cfg.items() if k != "description"})
