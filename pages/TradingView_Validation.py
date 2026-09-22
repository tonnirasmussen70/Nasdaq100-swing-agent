from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from tradingview_parity_compare import compare, normalize_tradingview_export, prepare_python_reference


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_CSV = ROOT / "validation" / "tradingview" / "reference_2026-09-22.csv"
REFERENCE_MANIFEST = ROOT / "validation" / "tradingview" / "reference_2026-09-22.json"


st.set_page_config(page_title="TradingView Validation", page_icon="🧪", layout="wide")
st.title("TradingView · signal-paritet")
st.caption(
    "Sammenlign en TradingView chart-data eksport med den frosne Python-reference. "
    "Dette tester signalregler og datapunkter — ikke broker fills eller live execution."
)

if not REFERENCE_CSV.exists() or not REFERENCE_MANIFEST.exists():
    st.error("Den frosne TradingView-reference mangler i repository.")
    st.stop()

manifest = json.loads(REFERENCE_MANIFEST.read_text(encoding="utf-8"))
reference_raw = pd.read_csv(REFERENCE_CSV)

meta = st.columns(4)
meta[0].metric("Reference-signaler", manifest.get("signal_count", len(reference_raw)))
meta[1].metric("Control", int((reference_raw["profile"].str.lower() == "control").sum()))
meta[2].metric("Challenger", int((reference_raw["profile"].str.lower() == "challenger").sum()))
meta[3].metric("Reference", "2026-09-22")

st.info(
    "Brug TradingViews standard 5-minutters OHLC-chart og signal-scriptet "
    "`tradingview/asian_breakout_signal_v6.pine`. Eksportér chart data separat for Control og Challenger."
)

left, right = st.columns([1, 1])
with left:
    profile = st.selectbox("Profil", ["control", "challenger"], format_func=str.title)
    uploaded = st.file_uploader("TradingView chart-data CSV", type=["csv"])
with right:
    price_tolerance = st.number_input(
        "Pris-tolerance (indekspoint)", min_value=0.0, value=0.25, step=0.05, format="%.2f"
    )
    metric_tolerance = st.number_input(
        "Metric-tolerance", min_value=0.0, value=0.002, step=0.001, format="%.3f"
    )

if uploaded is None:
    st.markdown("### Klar til første TradingView-test")
    st.write(
        "Når CSV-filen uploades her, køres sammenligningen direkte mod den frosne reference. "
        "Ingen filer eller strategiparametre ændres automatisk."
    )
    st.stop()

try:
    tradingview_raw = pd.read_csv(uploaded)
    tradingview = normalize_tradingview_export(tradingview_raw)
    python_reference = prepare_python_reference(reference_raw, profile)
    result = compare(
        python_reference,
        tradingview,
        price_tolerance=float(price_tolerance),
        metric_tolerance=float(metric_tolerance),
    )
except Exception as exc:
    st.error(f"Kunne ikke læse TradingView-eksporten: {exc}")
    st.stop()

st.markdown("### Resultat")
metrics = st.columns(5)
metrics[0].metric("Python signaler", result["python_signals"])
metrics[1].metric("TradingView signaler", result["tradingview_signals"])
metrics[2].metric("Timestamp match", f"{result['timestamp_match_rate_pct']:.1f}%")
metrics[3].metric(
    "Side match",
    "—" if result["side_match_rate_pct"] is None else f"{result['side_match_rate_pct']:.1f}%",
)
metrics[4].metric(
    "Numerisk match",
    "—" if result["numeric_within_tolerance_pct"] is None else f"{result['numeric_within_tolerance_pct']:.1f}%",
)

perfect_signal_parity = (
    result["timestamp_match_rate_pct"] == 100.0
    and result["side_match_rate_pct"] == 100.0
    and not result["missing_in_tradingview"]
    and not result["extra_in_tradingview"]
)
if perfect_signal_parity:
    st.success("Signal-paritet: 100% på timestamps og LONG/SHORT-retning.")
else:
    st.warning(
        "Signal-pariteten er ikke fuld. Undersøg først timestamps og LONG/SHORT-forskelle før P/L sammenlignes."
    )

mismatch_rows: list[dict[str, object]] = []
for detail in result.get("details", []):
    max_price = max((v for v in detail["price_deltas"].values() if v is not None), default=None)
    max_metric = max((v for v in detail["metric_deltas"].values() if v is not None), default=None)
    mismatch_rows.append(
        {
            "London time": detail["timestamp_london"],
            "Python": detail["python_side"],
            "TradingView": detail["tradingview_side"],
            "Side match": detail["side_match"],
            "Max price delta": max_price,
            "Max metric delta": max_metric,
        }
    )

if mismatch_rows:
    st.markdown("#### Matchede signaler")
    st.dataframe(pd.DataFrame(mismatch_rows), use_container_width=True, hide_index=True)

left, right = st.columns(2)
with left:
    st.markdown("#### Mangler i TradingView")
    missing = result.get("missing_in_tradingview", [])
    if missing:
        st.dataframe(pd.DataFrame({"London time": missing}), use_container_width=True, hide_index=True)
    else:
        st.success("Ingen")
with right:
    st.markdown("#### Ekstra TradingView-signaler")
    extra = result.get("extra_in_tradingview", [])
    if extra:
        st.dataframe(pd.DataFrame({"London time": extra}), use_container_width=True, hide_index=True)
    else:
        st.success("Ingen")

with st.expander("Maksimale numeriske afvigelser"):
    st.write("Prisfelter", result.get("max_price_delta", {}))
    st.write("Metrics", result.get("max_metric_delta", {}))
    st.caption(
        "Prisafvigelser kan skyldes forskelle mellem Yahoo/yfinance og TradingViews futures-feed. "
        "Timestamp/side-paritet vurderes derfor separat fra numerisk pris-paritet."
    )

st.download_button(
    "Download sammenligningsrapport (JSON)",
    data=json.dumps({"profile": profile, **result}, indent=2),
    file_name=f"tradingview_parity_{profile}.json",
    mime="application/json",
)
