import pandas as pd

from asian_breakout import evaluate_breakout


CFG = {
    "asian_session_start": "00:00",
    "asian_session_end": "07:30",
    "entry_window_start": "08:00",
    "entry_window_end": "10:00",
    "min_body_ratio": 0.60,
    "long_close_location_min": 0.80,
    "short_close_location_max": 0.20,
    "breakout_buffer_pct": 0.02,
    "stop_buffer_pct": 0.02,
    "min_asian_range_pct": 0.10,
    "max_asian_range_pct": 2.50,
    "reward_risk": 2.0,
    "risk_per_trade_pct": 1.0,
    "max_position_pct": 20.0,
    "account_value_dkk": 20000,
}


def frame_with_breakout(side: str) -> pd.DataFrame:
    idx = pd.date_range("2026-09-22 00:00", "2026-09-22 08:00", freq="5min", tz="Europe/London")
    data = pd.DataFrame({"Open": 100.0, "High": 100.2, "Low": 99.8, "Close": 100.0}, index=idx)
    if side == "LONG":
        data.loc[idx[-1], ["Open", "High", "Low", "Close"]] = [100.30, 101.10, 100.25, 101.05]
    else:
        data.loc[idx[-1], ["Open", "High", "Low", "Close"]] = [99.70, 99.75, 98.90, 98.95]
    return data


def test_long_breakout():
    signal = evaluate_breakout("QQQ", frame_with_breakout("LONG"), CFG, 6.4)
    assert signal is not None
    assert signal.side == "LONG"
    assert signal.reward_risk == 2.0
    assert signal.risk_dkk <= 200


def test_short_breakout():
    signal = evaluate_breakout("QQQ", frame_with_breakout("SHORT"), CFG, 6.4)
    assert signal is not None
    assert signal.side == "SHORT"
    assert signal.reward_risk == 2.0
    assert signal.risk_dkk <= 200


def test_no_signal_before_entry_window():
    frame = frame_with_breakout("LONG").iloc[:-7]
    assert evaluate_breakout("QQQ", frame, CFG, 6.4) is None
