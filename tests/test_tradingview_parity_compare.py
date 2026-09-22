from pathlib import Path

import pandas as pd

from tradingview_parity_compare import (
    compare,
    load_python_reference,
    load_tradingview_export,
    normalize_tradingview_export,
    prepare_python_reference,
)


def _python_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "profile": "control",
                "signal_time_london": "2026-09-21T08:10:00+01:00",
                "side": "LONG",
                "asian_high": 100.0,
                "asian_low": 99.0,
                "asian_range_pct": 1.005,
                "entry": 101.0,
                "stop": 100.0,
                "target": 103.0,
                "reward_risk": 2.0,
                "body_ratio": 0.75,
                "close_location": 0.90,
            },
            {
                "profile": "control",
                "signal_time_london": "2026-09-22T08:20:00+01:00",
                "side": "SHORT",
                "asian_high": 102.0,
                "asian_low": 100.0,
                "asian_range_pct": 1.980,
                "entry": 99.0,
                "stop": 100.0,
                "target": 97.0,
                "reward_risk": 2.0,
                "body_ratio": 0.80,
                "close_location": 0.10,
            },
        ]
    )


def _tv_frame(second_time: str = "2026-09-22T07:20:00Z") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": "2026-09-21T07:10:00Z",
                "Asian/London Breakout · Python parity: PARITY_SIGNAL_CODE": 1,
                "PARITY_ENTRY": 101.0,
                "PARITY_STOP": 100.0,
                "PARITY_TARGET": 103.0,
                "PARITY_ASIAN_HIGH": 100.0,
                "PARITY_ASIAN_LOW": 99.0,
                "PARITY_ASIAN_RANGE_PCT": 1.005,
                "PARITY_BODY_RATIO": 0.75,
                "PARITY_CLOSE_LOCATION": 0.90,
            },
            {
                "time": second_time,
                "Asian/London Breakout · Python parity: PARITY_SIGNAL_CODE": -1,
                "PARITY_ENTRY": 99.1,
                "PARITY_STOP": 100.0,
                "PARITY_TARGET": 97.0,
                "PARITY_ASIAN_HIGH": 102.0,
                "PARITY_ASIAN_LOW": 100.0,
                "PARITY_ASIAN_RANGE_PCT": 1.981,
                "PARITY_BODY_RATIO": 0.801,
                "PARITY_CLOSE_LOCATION": 0.101,
            },
        ]
    )


def _write_python(path: Path) -> None:
    _python_frame().to_csv(path, index=False)


def _write_tv(path: Path, second_time: str = "2026-09-22T07:20:00Z") -> None:
    _tv_frame(second_time).to_csv(path, index=False)


def test_compare_exact_signal_timestamps_with_tolerances(tmp_path: Path):
    py_path = tmp_path / "python.csv"
    tv_path = tmp_path / "tv.csv"
    _write_python(py_path)
    _write_tv(tv_path)

    py = load_python_reference(py_path, "control")
    tv = load_tradingview_export(tv_path)
    result = compare(py, tv, price_tolerance=0.25, metric_tolerance=0.002)

    assert result["matched_timestamps"] == 2
    assert result["timestamp_match_rate_pct"] == 100.0
    assert result["side_match_rate_pct"] == 100.0
    assert result["numeric_within_tolerance_pct"] == 100.0


def test_compare_reports_missing_and_extra_signals(tmp_path: Path):
    py_path = tmp_path / "python.csv"
    tv_path = tmp_path / "tv.csv"
    _write_python(py_path)
    _write_tv(tv_path, second_time="2026-09-23T07:20:00Z")

    result = compare(
        load_python_reference(py_path, "control"),
        load_tradingview_export(tv_path),
        price_tolerance=0.25,
        metric_tolerance=0.002,
    )

    assert result["matched_timestamps"] == 1
    assert len(result["missing_in_tradingview"]) == 1
    assert len(result["extra_in_tradingview"]) == 1
    assert result["timestamp_match_rate_pct"] < 100.0


def test_dataframe_helpers_support_streamlit_upload_flow():
    py = prepare_python_reference(_python_frame(), "control")
    tv = normalize_tradingview_export(_tv_frame())
    result = compare(py, tv, price_tolerance=0.25, metric_tolerance=0.002)

    assert len(py) == 2
    assert len(tv) == 2
    assert result["timestamp_match_rate_pct"] == 100.0
    assert result["side_match_rate_pct"] == 100.0
