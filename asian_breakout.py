from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass
class BreakoutSignal:
    ticker: str
    side: str
    signal_time: str
    asian_high: float
    asian_low: float
    asian_range_pct: float
    entry: float
    stop: float
    target: float
    reward_risk: float
    body_ratio: float
    close_location: float
    position_size_shares: int
    position_value_dkk: float
    risk_dkk: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ny_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    index = pd.DatetimeIndex(out.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    out.index = index.tz_convert("America/New_York")
    return out.sort_index()


def evaluate_breakout(
    ticker: str,
    frame: pd.DataFrame,
    cfg: dict[str, Any],
    usd_dkk: float,
) -> BreakoutSignal | None:
    """Evaluate the latest completed 5-minute bar for the London/Asian breakout.

    Times are expressed in Europe/London and converted from the market-data index,
    making the rule DST-aware. This engine only emits a paper-trading signal.
    """
    required = {"Open", "High", "Low", "Close"}
    if frame.empty or not required.issubset(frame.columns):
        return None

    data = _ny_index(frame.dropna(subset=list(required)))
    if len(data) < 2:
        return None
    london = data.tz_convert("Europe/London")
    latest = london.iloc[-1]
    signal_ts = london.index[-1]
    trade_date = signal_ts.date()

    session_start = pd.Timestamp(f"{trade_date} {cfg['asian_session_start']}", tz="Europe/London")
    session_end = pd.Timestamp(f"{trade_date} {cfg['asian_session_end']}", tz="Europe/London")
    entry_start = pd.Timestamp(f"{trade_date} {cfg['entry_window_start']}", tz="Europe/London")
    entry_end = pd.Timestamp(f"{trade_date} {cfg['entry_window_end']}", tz="Europe/London")

    if not (entry_start <= signal_ts < entry_end):
        return None

    asian = london[(london.index >= session_start) & (london.index < session_end)]
    if asian.empty:
        return None

    asian_high = float(asian["High"].max())
    asian_low = float(asian["Low"].min())
    midpoint = (asian_high + asian_low) / 2
    if midpoint <= 0:
        return None
    asian_range_pct = (asian_high - asian_low) / midpoint * 100
    if not (cfg["min_asian_range_pct"] <= asian_range_pct <= cfg["max_asian_range_pct"]):
        return None

    o, h, low, close = map(float, (latest["Open"], latest["High"], latest["Low"], latest["Close"]))
    candle_range = h - low
    if candle_range <= 0:
        return None
    body_ratio = abs(close - o) / candle_range
    if body_ratio < cfg["min_body_ratio"]:
        return None

    buffer_pct = cfg["breakout_buffer_pct"] / 100
    long_level = asian_high * (1 + buffer_pct)
    short_level = asian_low * (1 - buffer_pct)
    close_location = (close - low) / candle_range

    side: str | None = None
    if o > asian_high and close > long_level and close_location >= cfg["long_close_location_min"]:
        side = "LONG"
        entry = close
        stop = low - cfg["stop_buffer_pct"] / 100 * close
    elif o < asian_low and close < short_level and close_location <= cfg["short_close_location_max"]:
        side = "SHORT"
        entry = close
        stop = h + cfg["stop_buffer_pct"] / 100 * close
    else:
        return None

    risk_per_share = entry - stop if side == "LONG" else stop - entry
    if risk_per_share <= 0:
        return None

    rr = float(cfg["reward_risk"])
    target = entry + rr * risk_per_share if side == "LONG" else entry - rr * risk_per_share
    risk_budget = cfg["account_value_dkk"] * cfg["risk_per_trade_pct"] / 100
    if cfg.get("sizing_mode") == "normalized_r":
        # Research/paper mode: measure the strategy in R without pretending that
        # Yahoo's NQ=F quote has the economics of a cash share position.
        shares = 1
        actual_risk_dkk = risk_budget
        position_value_dkk = 0.0
    else:
        position_cap = cfg["account_value_dkk"] * cfg["max_position_pct"] / 100
        shares_by_risk = math.floor(risk_budget / (risk_per_share * usd_dkk))
        shares_by_cap = math.floor(position_cap / (entry * usd_dkk))
        shares = max(0, min(shares_by_risk, shares_by_cap))
        if shares == 0:
            return None
        actual_risk_dkk = shares * risk_per_share * usd_dkk
        position_value_dkk = shares * entry * usd_dkk

    return BreakoutSignal(
        ticker=ticker,
        side=side,
        signal_time=signal_ts.isoformat(),
        asian_high=round(asian_high, 2),
        asian_low=round(asian_low, 2),
        asian_range_pct=round(asian_range_pct, 3),
        entry=round(entry, 2),
        stop=round(stop, 2),
        target=round(target, 2),
        reward_risk=rr,
        body_ratio=round(body_ratio, 3),
        close_location=round(close_location, 3),
        position_size_shares=shares,
        position_value_dkk=round(position_value_dkk, 2),
        risk_dkk=round(actual_risk_dkk, 2),
    )
