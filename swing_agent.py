from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


NASDAQ_100_URL = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"


@dataclass
class Candidate:
    ticker: str
    close: float
    pattern: str
    setup_type: str
    entry: float
    stop: float
    target: float
    reward_risk: float
    beta: float
    return_1w_pct: float
    return_1m_pct: float
    return_3m_pct: float
    relative_strength_3m_pct: float
    volume_ratio: float
    score: float
    position_size_shares: int
    risk_dkk: float
    position_value_dkk: float
    failed_filters: list[str]


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def nasdaq100_tickers(symbol_file: Path | None = None, refresh: bool = False) -> list[str]:
    """Use a validated local universe; optionally refresh it from the public table."""
    symbol_file = symbol_file or Path(__file__).with_name("nasdaq100_symbols.txt")
    if refresh:
        tables = pd.read_html(NASDAQ_100_URL)
        for table in tables:
            normalized = {str(c).strip().lower(): c for c in table.columns}
            symbol_col = normalized.get("ticker") or normalized.get("symbol")
            if symbol_col is not None and len(table) >= 90:
                symbols = sorted(table[symbol_col].astype(str).str.replace(".", "-", regex=False).tolist())
                symbol_file.write_text("\n".join(symbols) + "\n", encoding="utf-8")
                return symbols
        raise RuntimeError("Could not locate a Nasdaq-100 constituents table.")
    symbols = [line.strip() for line in symbol_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(symbols) < 90 or len(symbols) != len(set(symbols)):
        raise RuntimeError("Local Nasdaq-100 universe failed validation.")
    return sorted(symbols)


def download_batch(tickers: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=True,
        prepost=False,
        actions=False,
        threads=True,
        progress=False,
        timeout=30,
    )
    result: dict[str, pd.DataFrame] = {}
    if len(tickers) == 1 and not isinstance(raw.columns, pd.MultiIndex):
        result[tickers[0]] = raw.dropna(how="all")
        return result
    for ticker in tickers:
        try:
            frame = raw[ticker].dropna(how="all").copy()
        except (KeyError, TypeError):
            continue
        if not frame.empty:
            result[ticker] = frame
    return result


def atr(frame: pd.DataFrame, period: int) -> pd.Series:
    previous_close = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - previous_close).abs(),
            (frame["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def candle_body(row: pd.Series) -> float:
    return abs(float(row["Close"]) - float(row["Open"]))


def detect_pattern(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    """Return one deterministic bullish 1H pattern from completed bars."""
    if len(frame) < 12:
        return None, None
    a, b, c = frame.iloc[-3], frame.iloc[-2], frame.iloc[-1]
    body = max(candle_body(c), 1e-9)
    full_range = max(float(c["High"] - c["Low"]), 1e-9)
    lower_wick = min(float(c["Open"]), float(c["Close"])) - float(c["Low"])
    upper_wick = float(c["High"]) - max(float(c["Open"]), float(c["Close"]))

    hammer = (
        c["Close"] > c["Open"]
        and lower_wick >= 2.0 * body
        and upper_wick <= body
        and body / full_range <= 0.40
    )
    engulfing = (
        b["Close"] < b["Open"]
        and c["Close"] > c["Open"]
        and c["Open"] <= b["Close"]
        and c["Close"] >= b["Open"]
    )
    morning_star = (
        a["Close"] < a["Open"]
        and candle_body(b) <= 0.40 * candle_body(a)
        and c["Close"] > c["Open"]
        and c["Close"] >= (a["Open"] + a["Close"]) / 2
    )
    inside_bar_breakout = (
        b["High"] < a["High"]
        and b["Low"] > a["Low"]
        and c["Close"] > a["High"]
        and c["Close"] > c["Open"]
    )

    prior = frame.iloc[-8:-3]
    pole = float(prior["Close"].iloc[-1] / prior["Close"].iloc[0] - 1)
    pullback = frame.iloc[-3:-1]
    orderly_pullback = bool((pullback["Low"].diff().dropna() <= 0).all())
    bull_flag = pole >= 0.025 and orderly_pullback and c["Close"] > pullback["High"].max()

    if morning_star:
        return "Morning star", "Reversal"
    if engulfing:
        return "Bullish engulfing", "Reversal"
    if hammer:
        return "Hammer", "Reversal"
    if inside_bar_breakout:
        return "Inside bar breakout", "Continuation"
    if bull_flag:
        return "Bull flag breakout", "Continuation"
    return None, None


def completed_daily(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    now = pd.Timestamp.now(tz="America/New_York")
    last_date = pd.Timestamp(frame.index[-1]).date()
    if last_date == now.date() and now.time() < pd.Timestamp("16:00").time():
        return frame.iloc[:-1]
    return frame


def calculate_beta(stock: pd.Series, benchmark: pd.Series) -> float:
    aligned = pd.concat([stock.pct_change(), benchmark.pct_change()], axis=1).dropna().tail(252)
    if len(aligned) < 126 or aligned.iloc[:, 1].var() == 0:
        return math.nan
    return float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / aligned.iloc[:, 1].var())


def screen_one(
    ticker: str,
    hourly: pd.DataFrame,
    daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame,
    cfg: dict[str, Any],
    usd_dkk: float,
) -> Candidate | None:
    hourly = hourly.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()
    daily = completed_daily(daily.dropna(subset=["Close", "Volume"]).copy())
    benchmark_daily = completed_daily(benchmark_daily.dropna(subset=["Close"]).copy())
    if len(hourly) < cfg["ema_slow"] + 5 or len(daily) < 253 or len(benchmark_daily) < 64:
        return None

    hourly["EMA50"] = hourly["Close"].ewm(span=cfg["ema_fast"], adjust=False).mean()
    hourly["EMA200"] = hourly["Close"].ewm(span=cfg["ema_slow"], adjust=False).mean()
    hourly["ATR"] = atr(hourly, cfg["atr_period"])
    last = hourly.iloc[-1]
    pattern, setup_type = detect_pattern(hourly)

    returns = {days: float(daily["Close"].iloc[-1] / daily["Close"].iloc[-1 - days] - 1) for days in (5, 21, 63)}
    benchmark_3m = float(benchmark_daily["Close"].iloc[-1] / benchmark_daily["Close"].iloc[-64] - 1)
    rs_3m = returns[63] - benchmark_3m
    beta = calculate_beta(daily["Close"], benchmark_daily["Close"])
    avg_volume = float(daily["Volume"].iloc[-21:-1].mean())
    volume_ratio = float(daily["Volume"].iloc[-1] / avg_volume) if avg_volume > 0 else math.nan

    checks = {
        "close_below_ema50": bool(last["Close"] > last["EMA50"]),
        "ema50_below_ema200": bool(last["EMA50"] > last["EMA200"]),
        "negative_1w": returns[5] > 0,
        "negative_1m": returns[21] > 0,
        "negative_3m": returns[63] > 0,
        "underperformed_ndx_3m": rs_3m > 0,
        "volume_not_above_20d": volume_ratio > 1,
        "beta_below_threshold": bool(not math.isnan(beta) and beta > cfg["beta_min"]),
        "no_confirmed_1h_pattern": pattern is not None,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if len(failed) > 1:
        return None

    atr_value = float(last["ATR"])
    if math.isnan(atr_value) or atr_value <= 0:
        return None
    entry = float(last["High"] + cfg["entry_atr_buffer"] * atr_value)
    swing_low = float(hourly["Low"].iloc[-cfg["swing_lookback_bars"] :].min())
    stop = swing_low - cfg["stop_atr_buffer"] * atr_value
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return None
    target = entry + max(cfg["target_atr_multiple"] * atr_value, cfg["minimum_reward_risk"] * risk_per_share)
    reward_risk = (target - entry) / risk_per_share
    risk_budget = cfg["account_value_dkk"] * cfg["risk_per_trade_pct"] / 100
    position_cap = cfg["account_value_dkk"] * cfg["max_position_pct"] / 100
    shares_by_risk = int(risk_budget / (risk_per_share * usd_dkk))
    shares_by_capital = int(position_cap / (entry * usd_dkk))
    position_size = max(0, min(shares_by_risk, shares_by_capital))
    actual_risk_dkk = position_size * risk_per_share * usd_dkk
    position_value_dkk = position_size * entry * usd_dkk

    trend_strength = max(0.0, float(last["Close"] / last["EMA50"] - 1))
    score = (
        30 * min(returns[63] / 0.25, 1.0)
        + 25 * min(max(rs_3m, 0) / 0.15, 1.0)
        + 20 * min(max(volume_ratio - 1, 0) / 1.0, 1.0)
        + 15 * min(trend_strength / 0.10, 1.0)
        + 10 * min(max(beta - cfg["beta_min"], 0) / 1.0, 1.0)
    )
    return Candidate(
        ticker=ticker,
        close=round(float(last["Close"]), 2),
        pattern=pattern or "None",
        setup_type=setup_type or "None",
        entry=round(entry, 2),
        stop=round(stop, 2),
        target=round(target, 2),
        reward_risk=round(reward_risk, 2),
        beta=round(beta, 2),
        return_1w_pct=round(returns[5] * 100, 2),
        return_1m_pct=round(returns[21] * 100, 2),
        return_3m_pct=round(returns[63] * 100, 2),
        relative_strength_3m_pct=round(rs_3m * 100, 2),
        volume_ratio=round(volume_ratio, 2),
        score=round(score, 1),
        position_size_shares=position_size,
        risk_dkk=round(actual_risk_dkk, 2),
        position_value_dkk=round(position_value_dkk, 2),
        failed_filters=failed,
    )


def previous_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"qualified": [], "near_miss": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"qualified": [], "near_miss": []}


def markdown_report(
    qualified: list[Candidate], near_miss: list[Candidate], changes: dict[str, list[str]], failures: list[str]
) -> str:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [f"# Nasdaq-100 Swing Screening — {stamp}", "", "Kun regelbaseret screening; ikke en købs- eller salgsanbefaling.", ""]
    lines += ["## Kvalificerede setups", ""]
    if qualified:
        lines.append("|Ticker|Setup|Score|Entry|Stop|Target|R/R|Antal|Position DKK|Risiko DKK|Beta|1W|1M|3M|RS 3M|Vol/20D|")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for c in qualified:
            lines.append(f"|{c.ticker}|{c.pattern}|{c.score:.1f}|{c.entry:.2f}|{c.stop:.2f}|{c.target:.2f}|{c.reward_risk:.2f}|{c.position_size_shares}|{c.position_value_dkk:.0f}|{c.risk_dkk:.0f}|{c.beta:.2f}|{c.return_1w_pct:.2f}%|{c.return_1m_pct:.2f}%|{c.return_3m_pct:.2f}%|{c.relative_strength_3m_pct:.2f}%|{c.volume_ratio:.2f}x|")
    else:
        lines.append("Ingen aktier opfyldte alle kriterier.")
    lines += ["", "## Ændringer siden seneste kørsel", ""]
    lines += [f"- Nye: {', '.join(changes['new']) or 'Ingen'}", f"- Udgĺet: {', '.join(changes['removed']) or 'Ingen'}"]
    lines += ["", "## Near-miss — præcis ét manglende filter", ""]
    if near_miss:
        lines.append("|Ticker|Manglende filter|1H-mønster|Score|")
        lines.append("|---|---|---|---:|")
        for c in near_miss:
            lines.append(f"|{c.ticker}|{c.failed_filters[0]}|{c.pattern}|{c.score:.1f}|")
    else:
        lines.append("Ingen near-miss kandidater.")
    if failures:
        lines += ["", "## Datakvalitet", "", f"Manglende eller utilstrækkelige data: {', '.join(sorted(failures))}."]
    return "\n".join(lines) + "\n"


def run(config_path: Path, refresh_universe: bool = False) -> Path:
    cfg = load_config(config_path)
    root = config_path.parent
    tickers = nasdaq100_tickers(refresh=refresh_universe)
    all_symbols = tickers + [cfg["benchmark"], cfg["usd_dkk_ticker"]]
    daily = download_batch(all_symbols, "2y", "1d")
    hourly = download_batch(tickers, "60d", "1h")
    benchmark = daily.get(cfg["benchmark"])
    if benchmark is None:
        raise RuntimeError(f"Benchmark data unavailable: {cfg['benchmark']}")
    fx_frame = daily.get(cfg["usd_dkk_ticker"])
    if fx_frame is None or fx_frame.dropna(subset=["Close"]).empty:
        raise RuntimeError(f"USD/DKK data unavailable: {cfg['usd_dkk_ticker']}")
    usd_dkk = float(fx_frame.dropna(subset=["Close"])["Close"].iloc[-1])

    qualified: list[Candidate] = []
    near_miss: list[Candidate] = []
    failures: list[str] = []
    for ticker in tickers:
        if ticker not in hourly or ticker not in daily:
            failures.append(ticker)
            continue
        result = screen_one(ticker, hourly[ticker], daily[ticker], benchmark, cfg, usd_dkk)
        if result is None:
            continue
        (qualified if not result.failed_filters else near_miss).append(result)
    qualified.sort(key=lambda item: item.score, reverse=True)
    near_miss.sort(key=lambda item: item.score, reverse=True)

    state_path = root / cfg["state_file"]
    old = previous_state(state_path)
    current_symbols = {c.ticker for c in qualified}
    old_symbols = set(old.get("qualified", []))
    changes = {"new": sorted(current_symbols - old_symbols), "removed": sorted(old_symbols - current_symbols)}

    output_dir = root / cfg["output_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    report_path = output_dir / f"nasdaq100_swing_{stamp}.md"
    report_path.write_text(markdown_report(qualified, near_miss, changes, failures), encoding="utf-8")
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "qualified": [asdict(c) for c in qualified],
        "near_miss": [asdict(c) for c in near_miss],
        "changes": changes,
        "data_failures": failures,
    }
    (output_dir / f"nasdaq100_swing_{stamp}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"qualified": sorted(current_symbols), "near_miss": sorted(c.ticker for c in near_miss)}, indent=2), encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rule-based Nasdaq-100 1H swing scanner")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--refresh-universe", action="store_true", help="Refresh Nasdaq-100 symbols before screening")
    args = parser.parse_args()
    print(run(args.config, refresh_universe=args.refresh_universe).resolve())


if __name__ == "__main__":
    main()
