import pandas as pd

from breakout_compare_runner import build_profile
from breakout_walkforward import compare_profiles, split_dates


BASE = {
    "ticker": "NQ=F",
    "asian_session_start": "00:00",
    "asian_session_end": "07:30",
    "entry_window_start": "08:00",
    "entry_window_end": "10:00",
    "min_body_ratio": 0.6,
    "long_close_location_min": 0.8,
    "short_close_location_max": 0.2,
    "breakout_buffer_pct": 0.02,
    "stop_buffer_pct": 0.02,
    "min_asian_range_pct": 0.1,
    "max_asian_range_pct": 2.5,
    "reward_risk": 2.0,
    "risk_per_trade_pct": 1.0,
    "max_position_pct": 20.0,
    "max_trades_per_day": 1,
    "sizing_mode": "normalized_r",
}

PROFILES = {
    "control": {"max_asian_range_pct": 2.5, "min_body_ratio": 0.6, "reward_risk": 2.0},
    "challenger": {"max_asian_range_pct": 1.0, "min_body_ratio": 0.6, "reward_risk": 2.5},
}


def synthetic_frame(days: int = 6) -> pd.DataFrame:
    frames = []
    start = pd.Timestamp("2026-09-14", tz="Europe/London")
    for day in pd.bdate_range(start=start, periods=days):
        idx = pd.date_range(day.normalize(), day.normalize() + pd.Timedelta(hours=10, minutes=30), freq="5min", tz="Europe/London")
        frame = pd.DataFrame({"Open": 100.0, "High": 100.2, "Low": 99.8, "Close": 100.0}, index=idx)
        frame.loc[day.normalize() + pd.Timedelta(hours=8), ["Open", "High", "Low", "Close"]] = [100.30, 101.10, 100.25, 101.05]
        frame.loc[day.normalize() + pd.Timedelta(hours=8, minutes=5), ["Open", "High", "Low", "Close"]] = [101.05, 103.20, 101.0, 103.0]
        frames.append(frame)
    return pd.concat(frames)


def test_build_profile_does_not_mutate_base():
    profile = build_profile(BASE, PROFILES["challenger"])
    assert profile["reward_risk"] == 2.5
    assert BASE["reward_risk"] == 2.0


def test_split_dates_is_chronological():
    first, second, split_date = split_dates(synthetic_frame(), 0.5)
    assert split_date is not None
    assert first.index.max() < second.index.min()


def test_compare_profiles_keeps_control_and_challenger_separate():
    result = compare_profiles(synthetic_frame(), BASE, PROFILES, 20000, 0.5)
    assert set(result["profiles"]) == {"control", "challenger"}
    assert result["profiles"]["control"]["settings"]["reward_risk"] == 2.0
    assert result["profiles"]["challenger"]["settings"]["reward_risk"] == 2.5
    assert result["profiles"]["control"]["validation"]["signals"] >= 1
    assert result["profiles"]["challenger"]["validation"]["signals"] >= 1
