from breakout_validation import cost_sensitivity, validation_status


def trade(result_r: float) -> dict:
    return {"status": "CLOSED", "result_r": result_r}


def test_collecting_until_minimum_sample():
    control = [trade(2.0), trade(-1.0), trade(-1.0)]
    challenger = [trade(2.5), trade(-1.0)]
    result = validation_status(control, challenger, minimum_closed_trades=30, costs_r=[0.0, 0.05])
    assert result["status"] == "COLLECTING_DATA"
    assert result["quantitative_gate_passed"] is False
    assert result["automatic_promotion"] is False
    assert result["challenger_closed_trades"] == 2
    assert len(result["cost_sensitivity"]) == 2


def test_review_required_only_after_quantitative_gate():
    control = [trade(2.0), trade(-1.0)] * 15
    challenger = [trade(2.5), trade(-1.0), trade(2.5)] * 10
    result = validation_status(control, challenger, minimum_closed_trades=30, costs_r=[0.0, 0.05, 0.1])
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["quantitative_gate_passed"] is True
    assert result["automatic_promotion"] is False
    assert result["costs_included_in_gate"] is False
    assert result["max_tested_cost_r_with_positive_challenger"] == 0.1


def test_negative_challenger_does_not_pass():
    control = [trade(2.0), trade(-1.0)] * 15
    challenger = [trade(-1.0)] * 30
    result = validation_status(control, challenger, minimum_closed_trades=30, costs_r=[0.0, 0.05])
    assert result["status"] == "COLLECTING_DATA"
    assert result["quantitative_gate_passed"] is False
    assert result["max_tested_cost_r_with_positive_challenger"] is None


def test_cost_stress_reduces_expectancy():
    challenger = [trade(2.5), trade(-1.0)] * 10
    rows = cost_sensitivity([], challenger, [0.0, 0.1])
    assert rows[1]["challenger"]["expectancy_r"] < rows[0]["challenger"]["expectancy_r"]
