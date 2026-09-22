import pandas as pd

from breakout_robustness import _split_by_date, evaluate_grid


BASE = {
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


def four_days() -> pd.DataFrame:
    frames = []
    for day in ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]:
        idx = pd.date_range(f"{day} 00:00", f"{day} 10:30", freq="5min", tz="Europe/London")
        frame = pd.DataFrame({"Open": 100.0, "High": 100.2, "Low": 99.8, "Close": 100.0}, index=idx)
        frame.loc[pd.Timestamp(f"{day} 08:00", tz="Europe/London"), ["Open", "High", "Low", "Close"]] = [100.30, 101.10, 100.25, 101.05]
        frame.loc[pd.Timestamp(f"{day} 08:05", tz="Europe/London"), ["Open", "High", "Low", "Close"]] = [101.05, 103.0, 101.0, 102.9]
        frames.append(frame)
    return pd.concat(frames)


def test_split_is_chronological():
    first, second, split_date = _split_by_date(four_days())
    assert split_date == "2026-09-23"
    assert first.index.max() < second.index.min()


def test_grid_returns_every_parameter_combination():
    rows = evaluate_grid(four_days(), BASE, 20000, [0.5, 1.0], [0.5, 0.6], [1.5, 2.0])
    assert len(rows) == 8
    assert all("full" in row and "first_half" in row and "second_half" in row for row in rows)


def test_stability_requires_positive_both_halves():
    rows = evaluate_grid(four_days(), BASE, 20000, [1.0], [0.5], [2.0])
    assert rows[0]["first_half"]["expectancy_r"] == 2.0
    assert rows[0]["second_half"]["expectancy_r"] == 2.0
