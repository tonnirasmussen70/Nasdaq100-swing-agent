from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


PRICE_FIELDS = {
    "entry": "PARITY_ENTRY",
    "stop": "PARITY_STOP",
    "target": "PARITY_TARGET",
    "asian_high": "PARITY_ASIAN_HIGH",
    "asian_low": "PARITY_ASIAN_LOW",
}
METRIC_FIELDS = {
    "asian_range_pct": "PARITY_ASIAN_RANGE_PCT",
    "body_ratio": "PARITY_BODY_RATIO",
    "close_location": "PARITY_CLOSE_LOCATION",
}


def _find_column(columns: list[str], marker: str) -> str:
    marker_upper = marker.upper()
    exact = [c for c in columns if c.upper() == marker_upper]
    if exact:
        return exact[0]
    suffix = [c for c in columns if c.upper().endswith(marker_upper)]
    if suffix:
        return suffix[0]
    contains = [c for c in columns if marker_upper in c.upper()]
    if contains:
        return contains[0]
    raise KeyError(f"TradingView export is missing required column marker: {marker}")


def _find_time_column(columns: list[str]) -> str:
    lowered = {c.lower(): c for c in columns}
    for candidate in ("time", "datetime", "timestamp", "date"):
        if candidate in lowered:
            return lowered[candidate]
    for column in columns:
        value = column.lower()
        if "time" in value or "date" in value:
            return column
    raise KeyError("Could not identify TradingView timestamp column")


def prepare_python_reference(frame: pd.DataFrame, profile: str) -> pd.DataFrame:
    required = {"profile", "signal_time_london", "side"}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Python reference is missing required columns: {sorted(missing)}")
    selected = frame[frame["profile"].astype(str).str.lower() == profile.strip().lower()].copy()
    selected["timestamp"] = pd.to_datetime(selected["signal_time_london"], utc=True).dt.tz_convert("Europe/London")
    selected["side_code"] = selected["side"].map({"LONG": 1, "SHORT": -1})
    return selected.sort_values("timestamp").reset_index(drop=True)


def load_python_reference(path: Path, profile: str) -> pd.DataFrame:
    return prepare_python_reference(pd.read_csv(path), profile)


def normalize_tradingview_export(raw: pd.DataFrame) -> pd.DataFrame:
    columns = list(raw.columns)
    time_col = _find_time_column(columns)
    signal_col = _find_column(columns, "PARITY_SIGNAL_CODE")

    rename: dict[str, str] = {time_col: "timestamp", signal_col: "side_code"}
    for python_name, marker in PRICE_FIELDS.items():
        rename[_find_column(columns, marker)] = python_name
    for python_name, marker in METRIC_FIELDS.items():
        rename[_find_column(columns, marker)] = python_name

    frame = raw.rename(columns=rename)[list(rename.values())].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Europe/London")
    frame["side_code"] = pd.to_numeric(frame["side_code"], errors="coerce").fillna(0).astype(int)
    frame = frame[frame["side_code"].isin([1, -1])].copy()
    for field in list(PRICE_FIELDS) + list(METRIC_FIELDS):
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    return frame.sort_values("timestamp").reset_index(drop=True)


def load_tradingview_export(path: Path) -> pd.DataFrame:
    return normalize_tradingview_export(pd.read_csv(path))


def compare(
    python_frame: pd.DataFrame,
    tradingview_frame: pd.DataFrame,
    price_tolerance: float,
    metric_tolerance: float,
) -> dict[str, Any]:
    py = python_frame.set_index("timestamp")
    tv = tradingview_frame.set_index("timestamp")
    py_times = set(py.index)
    tv_times = set(tv.index)
    matched_times = sorted(py_times & tv_times)
    missing_in_tv = sorted(py_times - tv_times)
    extra_in_tv = sorted(tv_times - py_times)

    details: list[dict[str, Any]] = []
    side_matches = 0
    numeric_matches = 0
    numeric_total = 0
    max_price_delta: dict[str, float] = {field: 0.0 for field in PRICE_FIELDS}
    max_metric_delta: dict[str, float] = {field: 0.0 for field in METRIC_FIELDS}

    for ts in matched_times:
        py_row = py.loc[ts]
        tv_row = tv.loc[ts]
        if isinstance(py_row, pd.DataFrame):
            py_row = py_row.iloc[0]
        if isinstance(tv_row, pd.DataFrame):
            tv_row = tv_row.iloc[0]

        side_match = int(py_row["side_code"]) == int(tv_row["side_code"])
        side_matches += int(side_match)
        price_deltas: dict[str, float | None] = {}
        metric_deltas: dict[str, float | None] = {}

        for field in PRICE_FIELDS:
            a, b = py_row.get(field), tv_row.get(field)
            delta = None if pd.isna(a) or pd.isna(b) else abs(float(a) - float(b))
            price_deltas[field] = delta
            if delta is not None:
                max_price_delta[field] = max(max_price_delta[field], delta)
                numeric_total += 1
                numeric_matches += int(delta <= price_tolerance)

        for field in METRIC_FIELDS:
            a, b = py_row.get(field), tv_row.get(field)
            delta = None if pd.isna(a) or pd.isna(b) else abs(float(a) - float(b))
            metric_deltas[field] = delta
            if delta is not None:
                max_metric_delta[field] = max(max_metric_delta[field], delta)
                numeric_total += 1
                numeric_matches += int(delta <= metric_tolerance)

        details.append(
            {
                "timestamp_london": ts.isoformat(),
                "python_side": "LONG" if int(py_row["side_code"]) == 1 else "SHORT",
                "tradingview_side": "LONG" if int(tv_row["side_code"]) == 1 else "SHORT",
                "side_match": side_match,
                "price_deltas": price_deltas,
                "metric_deltas": metric_deltas,
            }
        )

    matched = len(matched_times)
    union_count = len(py_times | tv_times)
    timestamp_match_rate = matched / union_count * 100 if union_count else 100.0
    side_match_rate = side_matches / matched * 100 if matched else None
    numeric_match_rate = numeric_matches / numeric_total * 100 if numeric_total else None

    return {
        "python_signals": len(py_times),
        "tradingview_signals": len(tv_times),
        "matched_timestamps": matched,
        "missing_in_tradingview": [ts.isoformat() for ts in missing_in_tv],
        "extra_in_tradingview": [ts.isoformat() for ts in extra_in_tv],
        "timestamp_match_rate_pct": round(timestamp_match_rate, 2),
        "side_match_rate_pct": None if side_match_rate is None else round(side_match_rate, 2),
        "numeric_within_tolerance_pct": None if numeric_match_rate is None else round(numeric_match_rate, 2),
        "price_tolerance": price_tolerance,
        "metric_tolerance": metric_tolerance,
        "max_price_delta": {k: round(v, 6) for k, v in max_price_delta.items()},
        "max_metric_delta": {k: round(v, 6) for k, v in max_metric_delta.items()},
        "details": details,
        "note": (
            "Signal/time parity and numeric price parity are reported separately. Different data feeds can create "
            "legitimate OHLC differences even when the rule implementation is identical."
        ),
    }


def run(
    python_reference: Path,
    tradingview_export: Path,
    profile: str,
    output: Path,
    price_tolerance: float,
    metric_tolerance: float,
) -> Path:
    py = load_python_reference(python_reference, profile)
    tv = load_tradingview_export(tradingview_export)
    payload = compare(py, tv, price_tolerance, metric_tolerance)
    payload["profile"] = profile
    payload["python_reference"] = str(python_reference)
    payload["tradingview_export"] = str(tradingview_export)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Python Asian breakout signals with a TradingView chart-data export")
    parser.add_argument("--python-reference", type=Path, default=Path("reports/tradingview_parity_reference.csv"))
    parser.add_argument("--tradingview-export", type=Path, required=True)
    parser.add_argument("--profile", choices=["control", "challenger"], required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/tradingview_parity_comparison.json"))
    parser.add_argument("--price-tolerance", type=float, default=0.25)
    parser.add_argument("--metric-tolerance", type=float, default=0.002)
    args = parser.parse_args()
    print(
        run(
            args.python_reference,
            args.tradingview_export,
            args.profile,
            args.output,
            args.price_tolerance,
            args.metric_tolerance,
        ).resolve()
    )


if __name__ == "__main__":
    main()
