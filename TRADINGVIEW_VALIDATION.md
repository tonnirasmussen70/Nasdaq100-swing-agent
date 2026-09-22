# TradingView validation playbook

This repository keeps the Python engine as the research/governance reference and uses TradingView as an independent chart/data validation layer.

## Two Pine scripts, two different jobs

- `tradingview/asian_breakout_signal_v6.pine` is the **signal-parity oracle**. It mirrors the Python entry rules and exposes named `PARITY_*` series for chart-data export.
- `tradingview/asian_breakout_strategy_v6.pine` is the **Strategy Tester wrapper**. It uses TradingView's broker emulator for entries/exits and is therefore not expected to be byte-for-byte identical to the Python trade-resolution engine.

Both scripts are Pine Script v6, use the IANA time zone `Europe/London`, and are intended for **standard 5-minute OHLC bars**.

## Frozen profiles

Control:

- Asian range: 00:00–07:30 London
- Entry window: 08:00–10:00 London
- Minimum Asian range: 0.10%
- Maximum Asian range: 2.50%
- Minimum candle body ratio: 0.60
- Reward/risk: 2.0R

Challenger differs only in:

- Maximum Asian range: 1.00%
- Reward/risk: 2.5R

Shared breakout rules remain identical to `asian_breakout.py`: 0.02% breakout buffer, 0.02% stop buffer, long close-location >= 0.80, short close-location <= 0.20, and at most one signal per London trading day.

## Frozen first parity baseline

The first 60-day Python parity export is frozen in `validation/tradingview/reference_2026-09-22.csv`, with provenance and checksum in `validation/tradingview/reference_2026-09-22.json`.

It contains 34 profile-signals across 19 London trading dates: 19 Control signals and 15 Challenger signals. The frozen CSV is protected by a SHA-256 integrity test so later Yahoo revisions or a fresh export cannot silently change the baseline used for the first TradingView comparison.

This snapshot is an implementation-parity fixture only. It is derived from Yahoo/yfinance NQ=F 5-minute data and must not be interpreted as independent market-data validation or evidence of strategy edge.

## Phase 1 — signal parity

1. Open a standard 5-minute Nasdaq futures chart in TradingView.
2. Paste `asian_breakout_signal_v6.pine` into Pine Editor and add it to the chart.
3. Run once with `Profile = Control` and once with `Profile = Challenger`.
4. Export chart data from TradingView. The indicator exposes `PARITY_SIGNAL_CODE`, `PARITY_ENTRY`, `PARITY_STOP`, `PARITY_TARGET`, `PARITY_ASIAN_HIGH`, `PARITY_ASIAN_LOW`, `PARITY_ASIAN_RANGE_PCT`, `PARITY_BODY_RATIO`, and `PARITY_CLOSE_LOCATION`.
5. Generate a fresh Python reference, when needed, with:

```bash
python breakout_tradingview_reference.py --period 60d
```

This creates `reports/tradingview_parity_reference.csv` plus a JSON manifest. The same export can also be produced as a GitHub Actions artifact by updating `.github/tradingview-reference-trigger.txt` on `main`.

For the first parity test, use the frozen baseline explicitly:

```bash
python tradingview_parity_compare.py \
  --python-reference validation/tradingview/reference_2026-09-22.csv \
  --tradingview-export path/to/tradingview.csv \
  --profile control
```

Run the same command with `--profile challenger` for the Challenger export.

The comparator reports timestamp overlap, side agreement, missing/extra signals and numeric deltas for entry, stop, target and session statistics. Default numeric tolerances are intentionally explicit and configurable (`--price-tolerance` and `--metric-tolerance`).

Compare **signal timestamps first**, then side, entry, stop, target and session statistics. Do not move to performance comparison until signal parity is understood. Different market-data feeds can legitimately produce OHLC differences, so timestamp/side parity and price parity are reported separately.

Important: the Python reference still uses Yahoo/yfinance. Matching TradingView against it proves implementation parity, not independent market-data correctness.

## Phase 2 — Strategy Tester

Use `tradingview/asian_breakout_strategy_v6.pine` on the same 5-minute chart. It uses `process_orders_on_close = true` because the Python signal entry is the breakout candle close. It also requests TradingView Bar Magnifier for more detailed historical fills when the user's plan supports it.

The Strategy Tester wrapper only opens a new position when flat. The Python paper journal currently enforces one signal per day but can record a later daily signal even if an earlier trade has not yet resolved. The Pine script therefore plots parity signals separately and marks signals skipped because a Strategy Tester position is still open. Treat such cases as execution-model differences, not signal-rule mismatches.

TradingView's broker emulator can resolve intrabar stop/target ordering differently from the Python backtest. The Python engine deliberately uses a conservative stop-first rule when a 5-minute bar touches both stop and target. Compare signal parity independently from PnL parity.

## Phase 3 — cross-data validation

After signal parity is stable:

- Compare NQ/MNQ continuous charts for a longer historical sample.
- Check selected periods against actual dated futures contracts to identify roll effects.
- Keep Control and Challenger frozen while collecting the prospective Python paper sample.
- Compare expectancy, profit factor, max drawdown and trade count, but investigate every material mismatch before treating it as evidence for or against the strategy.

## Phase 4 — forward paper validation

Only after historical discrepancies are understood, run TradingView alerts/paper trading alongside the GitHub monitor. TradingView remains a validation/signal channel; this repository does not enable automatic broker execution.

## Acceptance rule

A TradingView result is not sufficient by itself to promote the Challenger. Promotion still requires the prospective gate in `breakout_validation.py`, realistic execution costs, execution feasibility and human review.
