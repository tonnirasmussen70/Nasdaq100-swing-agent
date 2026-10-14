"""Standalone daily-bar swing screen for symbols outside Nasdaq-100.

Research/paper use only. No orders or automatic position inference.
"""
from __future__ import annotations

import math
import pandas as pd


def indicators(prices: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(prices.columns):
        raise ValueError("Missing OHLCV columns")
    d = prices.copy().sort_index()
    for col in required:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=list(required))
    if ((d["High"] < d[["Open", "Close", "Low"]].max(axis=1)) | (d["Low"] > d[["Open", "Close", "High"]].min(axis=1)) | (d["Low"] <= 0) | (d["Volume"] < 0)).any():
        raise ValueError("Inconsistent OHLCV data")
    if len(d) < 65:
        raise ValueError("At least 65 completed daily bars required")
    close = d["Close"]
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = up / down.replace(0, float("nan"))
    d["RSI14"] = (100 - 100 / (1 + rs)).where(down.ne(0), 100)
    d["MA20"] = close.rolling(20).mean()
    d["MA50"] = close.rolling(50).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["MACD"] = ema12 - ema26
    d["MACD_SIGNAL"] = d["MACD"].ewm(span=9, adjust=False).mean()
    prev = close.shift()
    true_range = pd.concat([d["High"]-d["Low"], (d["High"]-prev).abs(), (d["Low"]-prev).abs()],axis=1).max(axis=1)
    d["ATR14"] = true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    d["SWING_HIGH20"] = d["High"].shift().rolling(20).max()
    d["SWING_LOW10"] = d["Low"].shift().rolling(10).min()
    d["VOL20"] = d["Volume"].shift().rolling(20).median()
    return d


def screen(prices: pd.DataFrame, ticker: str = "IVN.TO", has_position: bool = False, entry_price: float | None = None) -> dict:
    d = indicators(prices)
    last, prev = d.iloc[-1], d.iloc[-2]
    close, atr = float(last["Close"]), float(last["ATR14"])
    if not (math.isfinite(close) and close > 0 and math.isfinite(atr) and atr > 0):
        raise ValueError("Invalid price or ATR")
    low = float(last["SWING_LOW10"])
    stop = min(low, close - 1.5 * atr)
    stop = max(0.01, stop - 0.25 * atr)
    risk = close - stop
    target = close + 2 * risk
    if risk <= 0 or not math.isfinite(risk):
        raise ValueError("Invalid stop distance")
    rsi_turn = float(prev["RSI14"]) < 35 and float(last["RSI14"]) > float(prev["RSI14"]) and float(last["RSI14"]) >= 30
    price_turn = close > float(prev["High"]) and close > float(prev["Close"])
    confirmation = (close > float(last["MA20"]) and float(prev["Close"]) <= float(prev["MA20"])) or (float(last["MACD"]) > float(last["MACD_SIGNAL"]) and float(prev["MACD"]) <= float(prev["MACD_SIGNAL"]))
    breakdown = close < low or (close < float(last["MA20"]) and float(last["MACD"]) < float(last["MACD_SIGNAL"]) and float(last["RSI14"]) < 40)
    if has_position:
        status = "SELL" if breakdown or (entry_price is not None and close < entry_price - 2*atr) else "HOLD"
    else:
        status = "BUY" if rsi_turn and price_turn and confirmation and risk > 0 else "WAIT"
    return {
        "ticker": ticker, "as_of": str(d.index[-1]), "status": status,
        "close": round(close, 2), "rsi14": round(float(last["RSI14"]), 1),
        "macd": round(float(last["MACD"]), 3), "macd_signal": round(float(last["MACD_SIGNAL"]), 3),
        "ma20": round(float(last["MA20"]), 2), "ma50": round(float(last["MA50"]), 2),
        "atr14": round(atr, 2), "support": round(low, 2),
        "resistance": round(float(last["SWING_HIGH20"]), 2),
        "entry": round(close, 2), "stop": round(stop, 2),
        "target": round(target, 2), "reward_risk": 2.0,
        "volume_ratio": round(float(last["Volume"] / last["VOL20"]), 2) if last["VOL20"] > 0 else None,
        "reason": "RSI recovery + price reversal + MA20/MACD confirmation" if status == "BUY"
            else "Trend/stop breakdown" if status == "SELL"
            else "Open position; no exit condition" if status == "HOLD"
            else "Waiting for confirmed reversal",
    }


def download_and_screen(ticker: str = "IVN.TO", has_position: bool = False, entry_price: float | None = None) -> dict:
    import yfinance as yf
    from datetime import datetime
    from zoneinfo import ZoneInfo
    frame = yf.download(ticker, period="2y", interval="1d", auto_adjust=True, progress=False)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if frame.empty:
        raise ValueError("No price data")
    # Yahoo's daily bar may be incomplete during the exchange session.
    now = datetime.now(ZoneInfo("America/Toronto"))
    if now.weekday() < 5 and (now.hour < 16 or (now.hour == 16 and now.minute < 15)):
        frame = frame.loc[pd.to_datetime(frame.index).date < now.date()]
    return screen(frame, ticker, has_position, entry_price)
