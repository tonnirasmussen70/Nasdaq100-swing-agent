import pandas as pd

from breakout_backtest import backtest


CFG = {
    "ticker": "NQ=F",
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
    "max_trades_per_day": 1,
    "sizing_mode": "normalized_r",
}


def synthetic_day() -> pd.DataFrame:
    idx = pd.date_range("2026-09-22 00:00", "2026-09-22 10:30", freq="5min", tz="Europe/London")
    frame = pd.DataFrame({"Open": 100.0, "High": 100.2, "Low": 99.8, "Close": 100.0}, index=idx)
    frame.loc[pd.Timestamp("2026-09-22 08:00", tz="Europe/London"), ["Open", "High", "Low", "Close"]] = [100.30, 101.10, 100.25, 101.05]
    frame.loc[pd.Timestamp("2026-09-22 08:05", tz="Europe/London"), ["Open", "High", "Low", "Close"]] = [101.05, 103.0, 101.0, 102.9]
    return frame


def test_backtest_limits_to_one_trade_per_day():
    trades = backtest(synthetic_day(), CFG, 20000)
    assert len(trades) == 1


def test_backtest_records_two_r_target_win():
    trades = backtest(synthetic_day(), CFG, 20000)
    assert trades[0]["status"] == "CLOSED"
    assert trades[0]["result_r"] == 2.0
    assert trades[0]["pnl_dkk"] == 400.0
