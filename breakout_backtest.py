from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from asian_breakout import evaluate_breakout
from breakout_runner import download_intraday, performance
from swing_agent import load_config


def simulate_trade(signal: dict[str, Any], future: pd.DataFrame) -> dict[str, Any]:
    side = signal["side"]
    stop = float(signal["stop"])
    target = float(signal["target"])
    for ts, bar in future.iterrows():
        hit_stop = float(bar["Low"]) <= stop if side == "LONG" else float(bar["High"]) >= stop
        hit_target = float(bar["High"]) >= target if side == "LONG" else float(bar["Low"]) <= target
        if not hit_stop and not hit_target:
            continue
        # Conservative when 5m OHLC cannot reveal intrabar ordering.
        result_r = -1.0 if hit_stop else float(signal["reward_risk"])
        return {
            **signal,
            "status": "CLOSED",
            "exit_time": pd.Timestamp(ts).isoformat(),
            "exit_price": stop if hit_stop else target,
            "result_r": result_r,
            "pnl_dkk": round(result_r * float(signal["risk_dkk"]), 2),
        }
    return {**signal, "status": "OPEN", "exit_time": None, "exit_price": None, "result_r": None, "pnl_dkk": None}


def backtest(frame: pd.DataFrame, strategy: dict[str, Any], account_value_dkk: float) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    data = frame.copy().sort_index()
    index = pd.DatetimeIndex(data.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    data.index = index

    london_index = data.index.tz_convert("Europe/London")
    dates = sorted(set(london_index.date))
    trades: list[dict[str, Any]] = []
    cfg = dict(strategy)
    cfg["account_value_dkk"] = account_value_dkk

    for trade_date in dates:
        mask = london_index.date == trade_date
        day = data.loc[mask]
        if day.empty:
            continue
        day_london = day.index.tz_convert("Europe/London")
        end = pd.Timestamp(f"{trade_date} {strategy['entry_window_end']}", tz="Europe/London")
        candidates = day[day_london < end]
        for i in range(1, len(candidates) + 1):
            history = data.loc[: candidates.index[i - 1]]
            signal = evaluate_breakout(strategy["ticker"], history, cfg, usd_dkk=1.0)
            if signal is None or pd.Timestamp(signal.signal_time).date() != trade_date:
                continue
            row = signal.to_dict()
            future = data[data.index > candidates.index[i - 1]]
            trades.append(simulate_trade(row, future))
            break  # max one trade per day
    return trades


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    strategy = dict(cfg["asian_breakout"])
    # Yahoo 5m history is intentionally treated as a short validation sample.
    period = strategy.get("backtest_period", "60d")
    frame = download_intraday(strategy["ticker"], period, strategy["data_interval"])
    trades = backtest(frame, strategy, cfg["account_value_dkk"])
    summary = performance(trades)
    summary["sample_warning"] = "Yahoo 5m data is a limited research sample; do not infer a durable edge from a small trade count."
    payload = {"ticker": strategy["ticker"], "period": period, "trades": trades, "performance": summary}
    output = config_path.parent / "reports" / "asian_breakout_backtest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Asian/London Nasdaq breakout")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
