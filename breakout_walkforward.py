from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from breakout_backtest import backtest
from breakout_compare_runner import build_profile
from breakout_runner import download_intraday, performance
from swing_agent import load_config


def summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    stats = performance(trades)
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("result_r") is not None]
    stats["signals"] = len(trades)
    stats["net_r"] = round(sum(float(t["result_r"]) for t in closed), 3)
    return stats


def split_dates(frame: pd.DataFrame, warmup_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    if frame.empty:
        return frame.copy(), frame.copy(), None
    data = frame.copy().sort_index()
    idx = pd.DatetimeIndex(data.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    data.index = idx
    london_dates = pd.Index(data.index.tz_convert("Europe/London").date).unique().sort_values()
    if len(london_dates) < 4:
        return data.copy(), data.iloc[0:0].copy(), None
    split_pos = max(1, min(len(london_dates) - 1, int(len(london_dates) * warmup_fraction)))
    split_date = london_dates[split_pos]
    dates = data.index.tz_convert("Europe/London").date
    return data[dates < split_date], data[dates >= split_date], str(split_date)


def compare_profiles(
    frame: pd.DataFrame,
    base: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    account_value_dkk: float,
    warmup_fraction: float,
) -> dict[str, Any]:
    development, validation, split_date = split_dates(frame, warmup_fraction)
    result: dict[str, Any] = {
        "split_date": split_date,
        "warning": (
            "The challenger was discovered using overlapping historical data, so this historical split is diagnostic, "
            "not a clean independent out-of-sample proof. Prospective paper results are the true forward test."
        ),
        "profiles": {},
    }
    for name, overrides in profiles.items():
        cfg = build_profile(base, overrides)
        result["profiles"][name] = {
            "settings": {
                "max_asian_range_pct": cfg["max_asian_range_pct"],
                "min_body_ratio": cfg["min_body_ratio"],
                "reward_risk": cfg["reward_risk"],
            },
            "development": summarize(backtest(development, cfg, account_value_dkk)),
            "validation": summarize(backtest(validation, cfg, account_value_dkk)),
            "full_sample": summarize(backtest(frame, cfg, account_value_dkk)),
        }
    return result


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    base = dict(cfg["asian_breakout"])
    validation_cfg = base.get("validation", {})
    profiles = validation_cfg.get("profiles", {})
    if not profiles:
        raise RuntimeError("No validation profiles configured")

    period = validation_cfg.get("period", base.get("backtest_period", "60d"))
    warmup_fraction = float(validation_cfg.get("development_fraction", 0.5))
    frame = download_intraday(base["ticker"], period, base["data_interval"])
    comparison = compare_profiles(frame, base, profiles, cfg["account_value_dkk"], warmup_fraction)
    payload = {
        "ticker": base["ticker"],
        "period": period,
        "mode": "fixed_profile_walk_forward_diagnostic",
        **comparison,
    }
    output = config_path.parent / "reports" / "asian_breakout_walkforward.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Fixed-profile Asian breakout walk-forward diagnostic")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
