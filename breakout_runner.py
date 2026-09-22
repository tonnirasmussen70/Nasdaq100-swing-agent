from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from asian_breakout import BreakoutSignal, evaluate_breakout
from report_io import write_json_if_changed
from swing_agent import load_config


def download_intraday(ticker: str, period: str, interval: str) -> pd.DataFrame:
    frame = yf.download(
        ticker,
        period=period,
        interval=interval,
        auto_adjust=True,
        prepost=True,
        actions=False,
        progress=False,
        timeout=30,
    )
    if isinstance(frame.columns, pd.MultiIndex):
        if ticker in frame.columns.get_level_values(0):
            frame = frame[ticker]
        else:
            frame.columns = frame.columns.get_level_values(0)
    return frame.dropna(how="all")


def load_journal(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_journal(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def signal_key(signal: BreakoutSignal) -> str:
    return f"{signal.ticker}:{signal.signal_time[:10]}"


def append_signal(path: Path, signal: BreakoutSignal) -> bool:
    rows = load_journal(path)
    key = signal_key(signal)
    if any(row.get("signal_key") == key for row in rows):
        return False
    row = signal.to_dict()
    row.update(
        {
            "signal_key": key,
            "status": "OPEN",
            "exit_time": None,
            "exit_price": None,
            "result_r": None,
            "pnl_dkk": None,
        }
    )
    rows.append(row)
    save_journal(path, rows)
    return True


def resolve_open_trades(path: Path, frame: pd.DataFrame) -> int:
    """Resolve paper trades conservatively. If stop and target occur in one bar, stop wins."""
    rows = load_journal(path)
    if not rows or frame.empty:
        return 0

    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    data = frame.copy()
    data.index = index
    resolved = 0

    for row in rows:
        if row.get("status") != "OPEN":
            continue
        opened = pd.Timestamp(row["signal_time"])
        if opened.tzinfo is None:
            opened = opened.tz_localize("Europe/London")
        opened_utc = opened.tz_convert("UTC")
        future = data[data.index.tz_convert("UTC") > opened_utc]
        if future.empty:
            continue

        side = row["side"]
        stop = float(row["stop"])
        target = float(row["target"])
        entry = float(row["entry"])
        risk = abs(entry - stop)

        for ts, bar in future.iterrows():
            hit_stop = float(bar["Low"]) <= stop if side == "LONG" else float(bar["High"]) >= stop
            hit_target = float(bar["High"]) >= target if side == "LONG" else float(bar["Low"]) <= target
            if not hit_stop and not hit_target:
                continue

            exit_price = stop if hit_stop else target
            result_r = -1.0 if hit_stop else float(row["reward_risk"])
            row["status"] = "CLOSED"
            row["exit_time"] = pd.Timestamp(ts).isoformat()
            row["exit_price"] = round(exit_price, 2)
            row["result_r"] = result_r
            row["pnl_dkk"] = round(result_r * float(row["risk_dkk"]), 2)
            resolved += 1
            break

    if resolved:
        save_journal(path, rows)
    return resolved


def performance(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    closed = [row for row in rows if row.get("status") == "CLOSED" and row.get("result_r") is not None]
    results = [float(row["result_r"]) for row in closed]
    if not results:
        return {"closed_trades": 0, "win_rate_pct": None, "expectancy_r": None, "profit_factor": None, "max_drawdown_r": None}

    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    equity = pd.Series(results).cumsum()
    drawdown = equity - equity.cummax()
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "closed_trades": len(results),
        "win_rate_pct": round(len(wins) / len(results) * 100, 2),
        "expectancy_r": round(sum(results) / len(results), 3),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "max_drawdown_r": round(abs(float(drawdown.min())), 3),
    }


def run(config_path: Path) -> dict[str, Any]:
    cfg = load_config(config_path)
    strategy = cfg["asian_breakout"]
    if not strategy.get("enabled", False):
        return {"status": "disabled"}

    ticker = strategy.get("ticker", "QQQ")
    frame = download_intraday(ticker, strategy["data_period"], strategy["data_interval"])
    journal_path = config_path.parent / strategy.get("journal_file", "state/asian_breakout_journal.json")
    resolved = resolve_open_trades(journal_path, frame)

    strategy_cfg = dict(strategy)
    strategy_cfg["account_value_dkk"] = cfg["account_value_dkk"]
    signal = evaluate_breakout(ticker, frame, strategy_cfg, usd_dkk=_usd_dkk(cfg))
    added = append_signal(journal_path, signal) if signal else False
    rows = load_journal(journal_path)
    payload = {
        "ticker": ticker,
        "signal": signal.to_dict() if signal else None,
        "new_signal": added,
        "resolved_trades": resolved,
        "performance": performance(rows),
        "journal_file": str(journal_path),
    }
    report_path = config_path.parent / strategy.get("report_file", "reports/asian_breakout_latest.json")
    report, _ = write_json_if_changed(
        report_path,
        payload,
        volatile_keys={"generated_at", "new_signal", "resolved_trades"},
    )
    return report


def _usd_dkk(cfg: dict[str, Any]) -> float:
    frame = yf.download(cfg["usd_dkk_ticker"], period="5d", interval="1d", auto_adjust=True, progress=False)
    if frame.empty:
        raise RuntimeError("USD/DKK data unavailable")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return float(close.dropna().iloc[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Nasdaq-100 Asian breakout paper runner")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(json.dumps(run(args.config), indent=2))


if __name__ == "__main__":
    main()
