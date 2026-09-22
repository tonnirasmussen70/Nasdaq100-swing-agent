from breakout_execution import ContractSpec, assess_signal, summarize_journal


def signal(entry=20000.0, stop=19980.0):
    return {"entry": entry, "stop": stop}


def test_mnq_spec_tick_value():
    mnq = ContractSpec("MNQ", "Micro E-mini Nasdaq-100", 2.0, 0.25)
    assert mnq.tick_value_usd == 0.50


def test_nnq_spec_tick_value():
    nnq = ContractSpec("NNQ", "E-nano Nasdaq-100", 0.2, 0.5)
    assert nnq.tick_value_usd == 0.10


def test_20_point_stop_can_be_too_large_for_mnq_at_200_dkk_budget():
    mnq = ContractSpec("MNQ", "Micro E-mini Nasdaq-100", 2.0, 0.25)
    result = assess_signal(signal(), mnq, usd_dkk=6.5, risk_budget_dkk=200.0)
    assert result.risk_per_contract_dkk == 260.0
    assert result.max_contracts_by_risk == 0
    assert result.feasible is False


def test_same_stop_is_feasible_with_nnq():
    nnq = ContractSpec("NNQ", "E-nano Nasdaq-100", 0.2, 0.5)
    result = assess_signal(signal(), nnq, usd_dkk=6.5, risk_budget_dkk=200.0)
    assert result.risk_per_contract_dkk == 26.0
    assert result.max_contracts_by_risk == 7
    assert result.feasible is True


def test_journal_summary_reports_feasibility_rate():
    mnq = ContractSpec("MNQ", "Micro E-mini Nasdaq-100", 2.0, 0.25)
    rows = [signal(20000, 19995), signal(20000, 19980)]
    summary = summarize_journal(rows, mnq, usd_dkk=6.5, risk_budget_dkk=200.0)
    assert summary["signals"] == 2
    assert summary["feasible_signals"] == 1
    assert summary["feasibility_pct"] == 50.0
