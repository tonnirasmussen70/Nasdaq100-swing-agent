import json
import re
from pathlib import Path

import pandas as pd

from breakout_tradingview_reference import build_reference_rows


ROOT = Path(__file__).resolve().parents[1]


def _markers() -> dict[str, float]:
    text = (ROOT / "tradingview" / "asian_breakout_signal_v6.pine").read_text(encoding="utf-8")
    pairs = re.findall(r"@parity\s+([\w.]+)=([0-9.]+)", text)
    return {key: float(value) for key, value in pairs}


def test_pine_profile_markers_match_python_config():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["asian_breakout"]
    profiles = cfg["validation"]["profiles"]
    markers = _markers()

    assert markers["min_asian_range_pct"] == cfg["min_asian_range_pct"]
    assert markers["long_close_location_min"] == cfg["long_close_location_min"]
    assert markers["short_close_location_max"] == cfg["short_close_location_max"]
    assert markers["breakout_buffer_pct"] == cfg["breakout_buffer_pct"]
    assert markers["stop_buffer_pct"] == cfg["stop_buffer_pct"]

    for name in ("control", "challenger"):
        assert markers[f"{name}.max_asian_range_pct"] == profiles[name]["max_asian_range_pct"]
        assert markers[f"{name}.min_body_ratio"] == profiles[name]["min_body_ratio"]
        assert markers[f"{name}.reward_risk"] == profiles[name]["reward_risk"]


def test_reference_export_contains_control_and_challenger_signal():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    base = dict(cfg["asian_breakout"])
    profiles = base["validation"]["profiles"]

    idx = pd.date_range("2026-09-22 00:00", "2026-09-22 08:00", freq="5min", tz="Europe/London")
    frame = pd.DataFrame({"Open": 100.0, "High": 100.2, "Low": 99.8, "Close": 100.0}, index=idx)
    frame.loc[idx[-1], ["Open", "High", "Low", "Close"]] = [100.30, 101.10, 100.25, 101.05]

    rows = build_reference_rows(frame, base, profiles, cfg["account_value_dkk"])
    by_profile = {row["profile"]: row for row in rows}

    assert set(by_profile) == {"control", "challenger"}
    assert by_profile["control"]["side"] == "LONG"
    assert by_profile["challenger"]["side"] == "LONG"
    assert by_profile["control"]["reward_risk"] == 2.0
    assert by_profile["challenger"]["reward_risk"] == 2.5
    assert by_profile["control"]["target"] < by_profile["challenger"]["target"]
