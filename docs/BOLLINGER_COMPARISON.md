# Bollinger Squeeze research comparison

## Main audit

Audited baseline: `30c6b19203af8578e2b643e8e46bbd04e98c8229`.
`daily_strategies.py` owns Volatility Breakout + RS; `swing_agent.py` is a
separate 1-hour core strategy and `breakout_*.py` concern Asian/London breakout.
Neither is an appropriate baseline for this daily Nasdaq-100 comparison.

Existing entry screen: close > SMA200, SMA50 > SMA200, SMA50 > its value five
sessions ago; close > maximum of previous 20 **closes**; 63-session return >
Nasdaq-100 (^NDX) return; volume >= 1.5 times the 20-session mean, including
today. Minimum history is 210 bars. ATR14 uses a simple rolling mean.
Existing stop: max(prior 20-close maximum - 0.5 ATR, close - 1.75 ATR), rounded
to cents. The live report quotes entry at signal close and a 2R target, but
does not execute trades, manage positions, or define holding time.

Audit limits retained to preserve defaults: the live scanner can include an
unfinished daily bar if run during a session, and its externally supplied
benchmark return is not date-aligned per ticker. Scheduled scans run after
US close. The new historical engine requires aligned completed daily bars.
The bundled universe is a current snapshot, not historical membership.
No claim is made that the live quote was executable at the signal close.

## Optional behavior

Default `python daily_strategies.py` keeps the old report schema and signal
calculations. `--bollinger-filter` requires a squeeze in the preceding five
sessions for the existing breakout. `--watch` adds a separate `watch` list:
current squeeze + existing trend + RS, price at/below upper band, and no
existing breakout. WATCH requires no volume confirmation, is observation
only, and never enters the backtest or places orders. Both flags default off.
Pullback logic, ranking, and the 1-hour and Asian strategies are unchanged.
The UI displays optional report fields when present and accepts older reports.

Bollinger definitions are fixed research choices, not optimized parameters:
20-session SMA +/- 2 population standard deviations; bandwidth = (upper-lower)
/ SMA. A squeeze is bandwidth <= the 20th percentile of the **preceding**
126 bandwidth observations. Full history is required (first eligibility at
bar 146). Recent squeeze excludes the breakout bar and covers five sessions.

- A: existing daily breakout + RS.
- B: A plus recent squeeze.
- C: existing trend, RS and volume confirmation, recent squeeze, close crosses
  above the **previous session's** upper band (previous close <= that band).
  The 20-close breakout condition is replaced by the Bollinger crossing.

## Comparable execution

All variants use the same data, dates, symbols, allocation and execution.
Signals form only after completed bar t; entry is at t+1 open plus 5 bps
slippage and 5 bps commission. Costs apply on both sides (20 bps round trip).
The signal-date stop above is frozen, with target 2R from actual entry fill.
An opening price at/below stop invalidates entry; counts are reported.
Fractional shares are allowed. Each accepted symbol receives an equal initial
cash sleeve, fully invested on its signals, independently compounded, never
rebalanced. One position per symbol, no borrowing; idle sleeves earn zero.
This allocation is a comparison convention, not an existing live rule.

Stop gaps fill at open less slippage; other stops at stop less slippage.
Target fills are capped at target less slippage, including favorable gaps.
If daily high and low touch both levels, stop wins. The entry bar can stop out.
Time exit: next open after 20 full exposure sessions. The final available bar
liquidates at close with costs. No entry is created from the final signal bar.
There are no same-bar close entries, future rankings or full-sample quantiles.

Daily equity marks open positions at closing liquidation value (including
exit costs). Net return and maximum drawdown are portfolio metrics, with
initial capital included in the high-water mark. Profit Factor is gross
positive / absolute gross negative **net-of-cost sleeve P&L** (equal initial
weights cancel). Expectancy is the average net trade return and average net
trade R using initial stop risk; these are not annualized portfolio returns.
Profit Factor is null when there are no losing trades; expectancy is null
when there are no trades. Max drawdown is reported as a negative percentage.

## Data and reproducibility

Run `python bollinger_backtest.py` to download adjusted Yahoo daily OHLCV from
2015-01-01 for warmup and compare 2016-01-01 through 2026-10-23 (end exclusive
2026-10-24). The output `reports/bollinger_comparison/summary.json` records
generation/cache modification times, package versions, accepted/rejected names, coverage, per-file SHA256 hashes and
execution assumptions; `equity.csv` and `trades.csv` expose the calculations.
Raw prices are cached in `work/bollinger_prices`. Repeat unchanged cached data
with `python bollinger_backtest.py --offline`; do not mix caches from different
runs. The CI comparison artifact includes raw prices and calculated outputs.

Symbols with download failure, invalid OHLCV, fewer than 210 bars or missing
interior benchmark sessions are excluded from **all** variants and reported.
OHLC comparisons allow only machine-precision roundoff (relative/absolute
tolerance 1e-10); raw prices are never repaired or imputed.
Later IPOs keep their sleeve in cash until enough history exists. A series
ending early is liquidated at its last available close, then remains cash;
this can be optimistic for delisted/untradeable securities. Read coverage
before relying on any comparison, especially partial provider downloads.

This is a current-universe, adjusted-price research test with survivorship
and selection bias: historical constituents, delisted names and point-in-time
corporate actions are unavailable. It prevents look-ahead in indicator and
execution timing but cannot remove universe/provider revision bias. OHLC
bars cannot reveal intraday order or liquidity. Costs are assumptions, not
broker quotes; spread, impact, taxes, FX, borrow, interest and dividend cash
accounting are not separately modeled. Adjusted prices approximate total
return. No walk-forward tuning, parameter sweep, or out-of-sample validation
is claimed. A/B/C alone cannot establish investability or a superior strategy.

## Validation

The frozen baseline fixture is copied from the audited main SHA. Regression
tests compare complete default payloads across many historical prefixes,
including positive pullback and breakout cases, and compare engine A signals
to live A. Other tests check causal prefix invariance, Bollinger warmup,
WATCH separation, short histories, gap fills, stop-first ambiguity, time and
end liquidation, costs, drawdown from initial capital, and missing sessions.
The dedicated PR workflow runs the full suite and historical comparison,
then uploads data/results without committing generated output to main.

## Observed results (2026-10-24 snapshot)

Period: 2016-01-01 to 2026-10-23, 99 accepted of 103 requested symbols.
Excluded: EA, HONA and SPCX (insufficient history); WBD (an OHLC row has
zero opening price). Raw-data hashes, all trades and daily equity accompany
this change in `reports/bollinger_comparison/` (raw prices in the CI artifact).

| Variant | Net return | Profit Factor | Max drawdown | Trades | Mean net trade return | Mean net R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A: existing | 14.62% | 1.258 | -2.24% | 2,160 | 0.512% | 0.037 |
| B: A + squeeze | 5.72% | 1.275 | -1.55% | 919 | 0.615% | 0.084 |
| C: BB squeeze breakout + RS | 4.93% | 1.338 | -0.88% | 658 | 0.753% | 0.148 |

These are cumulative portfolio returns over the whole period, after assumed
costs; they are not annual returns. Gap-invalidated entries: A 82, B 31, C 21.
The filter reduces trading frequency and drawdown and improves average trade
statistics, but lowers total return. Cash-heavy independent sleeves and current
universe selection materially affect these figures. This does not support
replacing the default strategy; options remain off. Re-downloads may revise
the dataset, so compare hashes before comparing different runs.
