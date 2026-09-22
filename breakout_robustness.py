from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

import pandas as pd

from breakout_backtest import backtest
from breakout_runner import download_intraday, performance
from swing_agent import load_config


def _summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    stats = performance(trades)
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("result_r") is not None]
    stats["net_r"] = round(sum(float(t["result_r"]) for t in closed), 3)
    stats["signals"] = len(trades)
    return stats


def _split_by_date(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
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
    split_pos = len(london_dates) // 2
    split_date = london_dates[split_pos]
    dates = data.index.tz_convert("Europe/London").date
    return data[dates < split_date], data[dates >= split_date], str(split_date)


def evaluate_grid(
    frame: pd.DataFrame,
    strategy: dict[str, Any],
    account_value_dkk: float,
    max_range_values: list[float],
    body_values: list[float],
    reward_risk_values: list[float],
) -> list[dict[str, Any]]:
    first, second, split_date = _split_by_date(frame)
    rows: list[dict[str, Any]] = []

    for max_range, body, rr in itertools.product(max_range_values, body_values, reward_risk_values):
        cfg = dict(strategy)
        cfg["max_asian_range_pct"] = float(max_range)
        cfg["min_body_ratio"] = float(body)
        cfg["reward_risk"] = float(rr)

        full_stats = _summary(backtest(frame, cfg, account_value_dkk))
        first_stats = _summary(backtest(first, cfg, account_value_dkk))
        second_stats = _summary(backtest(second, cfg, account_value_dkk)) if not second.empty else _summary([])

        stable_positive = (
            first_stats.get("closed_trades", 0) >= 3
            and second_stats.get("closed_trades", 0) >= 3
            and (first_stats.get("expectancy_r") or 0) > 0
            and (second_stats.get("expectancy_r") or 0) > 0
            and (full_stats.get("profit_factor") or 0) > 1
        )

        rows.append(
            {
                "max_asian_range_pct": float(max_range),
                "min_body_ratio": float(body),
                "reward_risk": float(rr),
                "split_date": split_date,
                "stable_positive": stable_positive,
                "full": full_stats,
                "first_half": first_stats,
                "second_half": second_stats,
            }
        )
    return rows


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    strategy = dict(cfg["asian_breakout"])
    robustness = strategy.get("robustness", {})
    period = robustness.get("period", strategy.get("backtest_period", "60d"))
    frame = download_intraday(strategy["ticker"], period, strategy["data_interval"])

    rows = evaluate_grid(
        frame,
        strategy,
        cfg["account_value_dkk"],
        robustness.get("max_asian_range_pct", [0.4, 0.5, 0.6, 0.75, 1.0, 2.5]),
        robustness.get("min_body_ratio", [0.5, 0.6, 0.7]),
        robustness.get("reward_risk", [1.5, 2.0, 2.5]),
    )

    stable = [row for row in rows if row["stable_positive"]]
    payload = {
        "ticker": strategy["ticker"],
        "period": period,
        "combination_count": len(rows),
        "stable_positive_count": len(stable),
        "warning": (
            "Sensitivity results are exploratory. The Yahoo 5-minute sample is short, "
            "and no parameter set should be promoted to the active strategy from this sample alone."
        ),
        "results": rows,
    }
    output = config_path.parent / "reports" / "asian_breakout_robustness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Asian/London breakout robustness sweep")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
