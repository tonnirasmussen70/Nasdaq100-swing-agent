from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "validation" / "tradingview" / "reference_2026-09-22.csv"
MANIFEST_PATH = ROOT / "validation" / "tradingview" / "reference_2026-09-22.json"


def test_frozen_tradingview_reference_snapshot_is_intact():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    csv_bytes = CSV_PATH.read_bytes()
    frame = pd.read_csv(CSV_PATH)

    assert hashlib.sha256(csv_bytes).hexdigest() == manifest["csv_sha256"]
    assert len(frame) == manifest["signal_count"] == 34
    assert frame["signal_time_london"].str[:10].nunique() == manifest["unique_signal_dates"] == 19
    assert frame.groupby("profile").size().to_dict() == {"challenger": 15, "control": 19}
    assert not frame.duplicated(subset=["profile", "signal_time_london"]).any()


def test_frozen_reference_has_expected_parity_columns():
    frame = pd.read_csv(CSV_PATH)
    assert list(frame.columns) == [
        "profile",
        "signal_time_london",
        "side",
        "asian_high",
        "asian_low",
        "asian_range_pct",
        "entry",
        "stop",
        "target",
        "reward_risk",
        "body_ratio",
        "close_location",
    ]
    assert set(frame["side"]) <= {"LONG", "SHORT"}
