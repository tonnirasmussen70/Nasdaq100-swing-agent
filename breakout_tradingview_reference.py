from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from breakout_backtest import backtest
from breakout_runner import download_intraday
from swing_agent import load_config


REFERENCE_FIELDS = [
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


def build_reference_rows(
    frame: pd.DataFrame,
    base_strategy: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    account_value_dkk: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile_name, overrides in profiles.items():
        strategy = dict(base_strategy)
        strategy.update(overrides)
        trades = backtest(frame, strategy, account_value_dkk)
        for trade in trades:
            signal_time = pd.Timestamp(trade["signal_time"])
            if signal_time.tzinfo is None:
                signal_time = signal_time.tz_localize("Europe/London")
            else:
                signal_time = signal_time.tz_convert("Europe/London")
            rows.append(
                {
                    "profile": profile_name,
                    "signal_time_london": signal_time.isoformat(),
                    "side": trade["side"],
                    "asian_high": trade["asian_high"],
                    "asian_low": trade["asian_low"],
                    "asian_range_pct": trade["asian_range_pct"],
                    "entry": trade["entry"],
                    "stop": trade["stop"],
                    "target": trade["target"],
                    "reward_risk": trade["reward_risk"],
                    "body_ratio": trade["body_ratio"],
                    "close_location": trade["close_location"],
                }
            )
    return sorted(rows, key=lambda row: (row["signal_time_london"], row["profile"]))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REFERENCE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run(config_path: Path, period: str | None = None) -> tuple[Path, Path]:
    cfg = load_config(config_path)
    strategy = dict(cfg["asian_breakout"])
    validation = strategy.get("validation", {})
    profiles = validation.get("profiles", {})
    if not profiles:
        raise RuntimeError("No validation profiles configured")

    selected_period = period or validation.get("period") or strategy.get("backtest_period", "60d")
    frame = download_intraday(strategy["ticker"], selected_period, strategy["data_interval"])
    rows = build_reference_rows(frame, strategy, profiles, float(cfg["account_value_dkk"]))

    root = config_path.parent
    csv_path = root / "reports" / "tradingview_parity_reference.csv"
    manifest_path = root / "reports" / "tradingview_parity_reference.json"
    write_csv(csv_path, rows)
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ticker": strategy["ticker"],
        "period": selected_period,
        "interval": strategy["data_interval"],
        "timezone": "Europe/London",
        "profiles": profiles,
        "signal_count": len(rows),
        "csv": str(csv_path),
        "warning": (
            "This reference uses the same Yahoo/yfinance 5-minute source as the Python research engine. "
            "It is for signal parity against TradingView, not independent performance validation."
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return csv_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Python Asian breakout signals for TradingView parity checks")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--period", default=None, help="Optional yfinance period override, e.g. 60d")
    args = parser.parse_args()
    csv_path, manifest_path = run(args.config, args.period)
    print(csv_path.resolve())
    print(manifest_path.resolve())


if __name__ == "__main__":
    main()
