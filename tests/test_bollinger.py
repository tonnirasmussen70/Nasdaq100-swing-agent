import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import daily_strategies as daily
from bollinger import features
from bollinger_backtest import compare, metrics, signals, simulate, validate


def bars(n=330):
    rng = np.random.default_rng(17)
    c = 80 * np.exp(np.cumsum(rng.normal(.002, .015, n)))
    return pd.DataFrame({'Open': c*.999, 'High': c*1.02, 'Low': c*.98,
                         'Close': c, 'Volume': rng.integers(100, 1000, n)},
                        index=pd.bdate_range('2020-01-01', periods=n))


def test_features_and_signals_are_prefix_invariant():
    d = bars()
    full = features(d.Close)
    ss = signals(d, d.assign(Close=d.Close*.8))
    for end in [145, 210, 260, 320]:
        pd.testing.assert_frame_equal(features(d.Close.iloc[:end]), full.iloc[:end])
        pd.testing.assert_frame_equal(signals(d.iloc[:end], d.iloc[:end].assign(Close=d.Close.iloc[:end]*.8)), ss.iloc[:end])
    assert not full['squeeze'].iloc[:145].any()
    assert full.bb_upper.iloc[19] == pytest.approx(d.Close.iloc[:20].mean()+2*d.Close.iloc[:20].std(ddof=0))


def test_defaults_match_frozen_main_and_backtest_a(monkeypatch):
    spec = importlib.util.spec_from_file_location('legacy', Path(__file__).parent/'fixtures/legacy_daily_strategies.py')
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    d = bars(500)
    benchmark = d.assign(Close=np.linspace(100, 101, len(d)))
    ss = signals(d, benchmark)
    counts = [0, 0]
    for end in range(210, len(d)+1):
        prefix = d.iloc[:end]
        monkeypatch.setattr(daily.yf, 'download', lambda *a, **kw: prefix.copy())
        nr = benchmark.Close.iloc[end-1]/benchmark.Close.iloc[end-64]-1
        old = legacy.one('TEST', nr)
        new = daily.one('TEST', nr)
        assert new == old
        assert bool(ss.A.iloc[end-1]) == (new[1] is not None)
        counts[0] += new[0] is not None
        counts[1] += new[1] is not None
        filtered = daily.one('TEST', nr, bollinger_filter=True)
        assert filtered[0] == old[0]
        if filtered[1]:
            assert filtered[1] == old[1]
    assert all(counts), 'Regression sample must exercise both strategies'


def test_watch_is_early_and_does_not_change_buy(monkeypatch):
    d = bars()
    c = np.linspace(80, 150, len(d))
    c[-1] = c[-2] - .2
    d.loc[:, ['Open', 'High', 'Low', 'Close']] = np.column_stack([c, c+1, c-1, c])
    monkeypatch.setattr(daily.yf, 'download', lambda *a, **kw: d.copy())
    monkeypatch.setattr(daily, 'bollinger_features', lambda c: pd.DataFrame(
        {'squeeze': True, 'recent_squeeze': True, 'bb_upper': c*1.1}, index=c.index))
    base = daily.one('TEST', -1.)
    extended = daily.one('TEST', -1., include_watch=True)
    assert extended[:2] == base
    assert extended[2]['status'] == 'WATCH'
    assert extended[1] is None


def test_short_history_tuple(monkeypatch):
    monkeypatch.setattr(daily.yf, 'download', lambda *a, **kw: bars(20))
    assert daily.one('X', 0) is None
    assert daily.one('X', 0, include_watch=True) == (None, None, None)


def execution_fixture():
    d = bars(5)
    d.loc[:, ['Open', 'High', 'Low', 'Close']] = [100., 101., 99., 100.]
    sig = pd.DataFrame({'A': [True, False, False, False, False], 'stop': 95.}, index=d.index)
    return d, sig


def test_next_open_and_stop_first_with_costs():
    d, sig = execution_fixture()
    d.iloc[1, d.columns.get_loc('High')] = 120
    d.iloc[1, d.columns.get_loc('Low')] = 90
    eq, ts, _ = simulate(d, sig, 'A', str(d.index[0]), str(d.index[-1]))
    t = ts[0]
    assert t['entry_date'] == str(d.index[1].date())
    assert t['reason'] == 'stop'
    assert t['entry'] == pytest.approx(100.05)
    assert t['exit'] == pytest.approx(94.9525)
    assert t['pnl'] < -.05
    assert eq.iloc[-1] == pytest.approx(1+t['pnl'])


def test_gap_stop_and_invalid_gap_entry():
    d, sig = execution_fixture()
    d.iloc[2, d.columns.get_loc('Open')] = 90
    d.iloc[2, d.columns.get_loc('Low')] = 89
    _, ts, _ = simulate(d, sig, 'A', str(d.index[0]), str(d.index[-1]), 0, 0)
    assert ts[0]['exit'] == 90
    d.iloc[1, d.columns.get_loc('Open')] = 94
    d.iloc[1, d.columns.get_loc('Low')] = 93
    _, ts, skipped = simulate(d, sig, 'A', str(d.index[0]), str(d.index[-1]))
    assert ts == [] and skipped == 1


def test_time_exit_and_final_liquidation():
    d, sig = execution_fixture()
    _, ts, _ = simulate(d, sig, 'A', str(d.index[0]), str(d.index[-1]), max_hold=1)
    assert ts[0]['exit_date'] == str(d.index[2].date())
    assert ts[0]['reason'] == 'time'
    _, ts, _ = simulate(d, sig, 'A', str(d.index[0]), str(d.index[-1]))
    assert ts[0]['reason'] == 'end_of_sample'


def test_metrics_initial_peak_and_no_trades():
    m = metrics(pd.Series([.9, .95]), [])
    assert m['max_drawdown_pct'] == pytest.approx(-10)
    assert m['net_return_pct'] == pytest.approx(-5)
    assert m['profit_factor'] is None and m['expectancy_r'] is None


def test_reject_duplicate_and_missing_sessions():
    d = bars()
    with pytest.raises(ValueError, match='unique'):
        validate(pd.concat([d, d.iloc[-1:]]))
    with pytest.raises(ValueError, match='missing interior'):
        compare({'X': d.drop(d.index[230])}, d, '2020-01-01', '2022-01-01')


def test_validation_tolerates_only_machine_precision():
    d, _ = execution_fixture()
    d.iloc[0, d.columns.get_loc('High')] = 100.-1e-12
    validate(d)
    d.iloc[0, d.columns.get_loc('High')] = 99.99
    with pytest.raises(ValueError, match='Invalid OHLCV'):
        validate(d)


def test_comparison_uses_same_calendar_and_costs_reduce_return():
    d = bars(500)
    c = np.linspace(100, 101, len(d))
    ndx = d.assign(Open=c, High=c+1, Low=c-1, Close=c)
    free, eq, _ = compare({'X': d}, ndx, '2020-01-01', '2022-01-01', fee_bps=0, slippage_bps=0)
    paid, _, _ = compare({'X': d}, ndx, '2020-01-01', '2022-01-01')
    assert list(eq) == ['A', 'B', 'C']
    assert free['A']['net_return_pct'] > paid['A']['net_return_pct']
