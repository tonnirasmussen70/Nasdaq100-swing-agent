"""Comparable A/B/C daily-bar research backtest; never places orders."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from bollinger import features
from daily_strategies import atr, universe

VARIANTS = ("A", "B", "C")


def validate(d):
    d = d.copy()
    d.index = pd.to_datetime(d.index).tz_localize(None)
    if d.index.has_duplicates or not d.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and sorted")
    cols = ["Open", "High", "Low", "Close", "Volume"]
    if not np.isfinite(d[cols].to_numpy()).all():
        raise ValueError("Non-finite OHLCV")
    # Adjusted-price CSV roundtrips can differ by a few machine ulps.
    hi = d[["Open", "Close", "Low"]].max(axis=1)
    lo = d[["Open", "Close", "High"]].min(axis=1)
    bad_hi = d.High.lt(hi) & ~np.isclose(d.High, hi, rtol=1e-10, atol=1e-10)
    bad_lo = d.Low.gt(lo) & ~np.isclose(d.Low, lo, rtol=1e-10, atol=1e-10)
    if ((d[cols[:4]] <= 0).any(axis=1) | (d.Volume < 0) | bad_hi | bad_lo).any():
        raise ValueError("Invalid OHLCV")
    return d


def signals(d, benchmark):
    c = d.Close
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    trend = (c > ma200) & (ma50 > ma200) & (ma50 > ma50.shift(5))
    ret = c / c.shift(63) - 1
    rs = ret > (benchmark.Close / benchmark.Close.shift(63) - 1).reindex(d.index)
    resistance = c.shift().rolling(20).max()
    volume = d.Volume / d.Volume.rolling(20).mean()
    ready = pd.Series(np.arange(len(d)) >= 209, index=d.index)
    common = trend & rs & volume.ge(1.5) & ready
    bb = features(c)
    a = common & c.gt(resistance)
    out = pd.DataFrame({"A": a, "B": a & bb.recent_squeeze,
                        "C": common & bb.bb_breakout})
    out["stop"] = pd.concat([resistance - .5 * atr(d), c - 1.75 * atr(d)], axis=1).max(axis=1).round(2)
    return out


def simulate(d, sig, variant, start, end, fee_bps=5., slippage_bps=5., max_hold=20):
    """One fully funded sleeve, no overlapping positions, next-open entries.

    Signal-close stop is frozen. Target is 2R from slipped next-open fill.
    Stop wins ambiguous daily bars; stop gaps fill at open, target gaps at target.
    Time exits occur at open after max_hold complete exposure sessions.
    """
    if fee_bps < 0 or slippage_bps < 0 or max_hold < 1:
        raise ValueError("Invalid execution assumptions")
    fee, slip = fee_bps / 10000, slippage_bps / 10000
    cash, pos, pending = 1., None, None
    marks, trades, skipped = {}, [], 0
    active = d.loc[(d.index >= pd.Timestamp(start)) & (d.index < pd.Timestamp(end))]
    for date, bar in active.iterrows():
        if pending is not None and pos is None:
            stop, signal_date = pending
            fill = float(bar.Open) * (1 + slip)
            if float(bar.Open) <= stop or fill <= stop or stop <= 0:
                skipped += 1
            else:
                qty = cash / (fill * (1 + fee))
                pos = dict(qty=qty, entry=fill, stop=stop, target=fill+2*(fill-stop),
                           initial=cash, risk=qty*(fill-stop), age=0,
                           signal_date=str(signal_date.date()), entry_date=str(date.date()))
                cash = 0.
            pending = None
        if pos is not None:
            price, reason = None, None
            if bar.Open <= pos['stop']:
                price, reason = float(bar.Open), 'gap_stop'
            elif pos['age'] >= max_hold:
                price, reason = float(bar.Open), 'time'
            elif bar.Low <= pos['stop']:
                price, reason = pos['stop'], 'stop'
            elif bar.High >= pos['target']:
                price, reason = pos['target'], 'target'
            elif date == active.index[-1]:
                price, reason = float(bar.Close), 'end_of_sample'
            if price is not None:
                exit_fill = price * (1-slip)
                cash = pos['qty'] * exit_fill * (1-fee)
                pnl = cash-pos['initial']
                trades.append(dict(variant=variant, signal_date=pos['signal_date'],
                                   entry_date=pos['entry_date'], exit_date=str(date.date()),
                                   entry=pos['entry'], exit=exit_fill, stop=pos['stop'],
                                   reason=reason, pnl=pnl, net_return=pnl/pos['initial'],
                                   net_r=pnl/pos['risk']))
                pos = None
            else:
                pos['age'] += 1
        marks[date] = cash if pos is None else pos['qty']*float(bar.Close)*(1-slip)*(1-fee)
        if pos is None and date != active.index[-1] and bool(sig.loc[date, variant]):
            pending = (float(sig.loc[date, 'stop']), date)
    return pd.Series(marks, dtype=float), trades, skipped


def metrics(equity, trades):
    pnl = pd.Series([x['pnl'] for x in trades], dtype=float)
    gains, losses = pnl.clip(lower=0).sum(), -pnl.clip(upper=0).sum()
    # Include initial capital in the high-water mark (first-day loss matters).
    peak = equity.cummax().clip(lower=1.)
    return dict(net_return_pct=float((equity.iloc[-1]-1)*100),
                profit_factor=float(gains/losses) if losses else None,
                max_drawdown_pct=float(((equity/peak)-1).min()*100),
                trades=len(trades), expectancy_pct=float(np.mean([x['net_return'] for x in trades])*100) if trades else None,
                expectancy_r=float(np.mean([x['net_r'] for x in trades])) if trades else None)


def validate_alignment(ticker, d, benchmark):
    if not d.index.isin(benchmark.index).all():
        raise ValueError(f'{ticker}: dates absent from benchmark')
    expected = benchmark.loc[d.index[0]:d.index[-1]].index
    if not d.index.equals(expected):
        raise ValueError(f'{ticker}: missing interior sessions')


def compare(prices, benchmark, start, end, **execution):
    benchmark = validate(benchmark)
    calendar = benchmark.index[(benchmark.index >= pd.Timestamp(start)) & (benchmark.index < pd.Timestamp(end))]
    if calendar.empty or not prices:
        raise ValueError('No comparable data')
    curves = {v: [] for v in VARIANTS}
    trades = {v: [] for v in VARIANTS}
    skipped = {v: 0 for v in VARIANTS}
    for ticker, raw in prices.items():
        d = validate(raw)
        validate_alignment(ticker, d, benchmark)
        sig = signals(d, benchmark)
        for variant in VARIANTS:
            eq, ts, n = simulate(d, sig, variant, start, end, **execution)
            curves[variant].append(eq.reindex(calendar).ffill().fillna(1.))
            trades[variant].extend(dict(t, ticker=ticker) for t in ts)
            skipped[variant] += n
    result, equities = {}, pd.DataFrame(index=calendar)
    for v in VARIANTS:
        equities[v] = pd.concat(curves[v], axis=1).mean(axis=1)
        result[v] = dict(metrics(equities[v], trades[v]), skipped_gap_entries=skipped[v])
    return result, equities, [t for v in VARIANTS for t in trades[v]]


def main():
    import yfinance as yf
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2016-01-01')
    parser.add_argument('--end', default='2026-10-24', help='Exclusive download endpoint')
    parser.add_argument('--cache', type=Path, default=Path('work/bollinger_prices'))
    parser.add_argument('--out', type=Path, default=Path('reports/bollinger_comparison'))
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    symbols, prices, failures, provenance = universe(), {}, {}, {}
    for ticker in ['^NDX', *symbols]:
        path = args.cache / (ticker.replace('^', '') + '.csv')
        try:
            if not args.offline:
                d = yf.download(ticker, start='2015-01-01', end=args.end,
                                auto_adjust=True, progress=False, threads=False)
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(0)
                if d.empty:
                    raise ValueError('No data returned')
                d.to_csv(path)
            d = validate(pd.read_csv(path, index_col=0, parse_dates=True))
            if len(d) < 210 or d.loc[args.start:args.end].empty:
                raise ValueError('Insufficient history')
            provenance[ticker] = dict(rows=len(d), first=str(d.index[0].date()),
                                     last=str(d.index[-1].date()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            provenance[ticker]['cache_modified_at_utc'] = pd.Timestamp(path.stat().st_mtime, unit='s', tz='UTC').isoformat()
            prices[ticker] = d
        except Exception as exc:
            failures[ticker] = str(exc)
    if '^NDX' not in prices:
        raise RuntimeError(f'Benchmark unavailable: {failures}')
    benchmark = prices.pop('^NDX')
    # Validate each name independently, keeping precisely the same accepted set for A/B/C.
    for ticker in list(prices):
        try:
            validate_alignment(ticker, prices[ticker], benchmark)
        except ValueError as exc:
            failures[ticker] = str(exc)
            del prices[ticker]
    result, eq, trades = compare(prices, benchmark, args.start, args.end)
    report = dict(source='Yahoo Finance via yfinance; adjusted daily OHLCV',
                  generated_at=pd.Timestamp.now(tz='UTC').isoformat(), offline=args.offline,
                  versions=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, yfinance=yf.__version__),
                  implementation_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                         for name in ['bollinger.py', 'bollinger_backtest.py', 'daily_strategies.py']},
                  start=args.start, end_exclusive=args.end, actual_last=str(eq.index[-1].date()),
                  requested_symbols=symbols, accepted_symbols=list(prices), failures=failures,
                  provenance=provenance, execution=dict(fee_bps_per_side=5, slippage_bps_per_side=5,
                  max_hold_sessions=20, allocation='Equal initial capital sleeves, no rebalancing or leverage'),
                  metrics=result)
    (args.out/'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    eq.to_csv(args.out/'equity.csv')
    pd.DataFrame(trades).to_csv(args.out/'trades.csv', index=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
