"""Causal daily Bollinger features; no trading side effects."""
from __future__ import annotations

import pandas as pd


def features(close: pd.Series) -> pd.DataFrame:
    """BB(20,2), population SD; threshold excludes today's bandwidth.

    Squeeze is bandwidth <= trailing 126-bar 20th percentile. A release
    may follow any squeeze in the previous five sessions (excluding today).
    Full windows are required; unavailable history never passes a filter.
    """
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std(ddof=0)
    upper, lower = mid + 2 * sd, mid - 2 * sd
    width = (upper - lower) / mid.where(mid > 0)
    threshold = width.shift().rolling(126).quantile(0.2)
    squeeze = width.le(threshold) & threshold.notna()
    recent = squeeze.shift(fill_value=False).rolling(5, min_periods=1).max().eq(1)
    cross = close.gt(upper.shift()) & close.shift().le(upper.shift())
    return pd.DataFrame({"bb_mid": mid, "bb_upper": upper, "bb_lower": lower,
                         "bb_width": width, "bb_threshold": threshold,
                         "squeeze": squeeze, "recent_squeeze": recent,
                         "bb_breakout": recent & cross})
