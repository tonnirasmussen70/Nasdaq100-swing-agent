from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "reports"
CONFIG_PATH = ROOT / "config.json"

FILTER_NAMES = {
    "close_below_ema50": "Kurs er ikke over EMA50",
    "ema50_below_ema200": "EMA50 er ikke over EMA200",
    "negative_1w": "1-uges afkast er ikke positivt",
    "negative_1m": "1-måneds afkast er ikke positivt",
    "negative_3m": "3-måneders afkast er ikke positivt",
    "underperformed_ndx_3m": "Underperformer Nasdaq-100 over 3 måneder",
    "volume_not_above_20d": "Volumen er ikke over 20-dages gennemsnittet",
    "beta_below_threshold": "Beta er ikke over minimum",
    "no_confirmed_1h_pattern": "Intet bekræftet bullish 1H-mønster",
}


def report_files(directory: Path = REPORT_DIR) -> list[Path]:
    return sorted(directory.glob("nasdaq100_swing_*.json"), reverse=True)


@st.cache_data(show_spinner=False)
def load_json(path: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_report(path: Path) -> dict[str, Any]:
    return load_json(str(path), path.stat().st_mtime_ns)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Ukendt"
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone().strftime("%d-%m-%Y kl. %H:%M %Z")
    except ValueError:
        return value


def candidate_frame(items: list[dict[str, Any]]) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    frame = pd.DataFrame(items)
    return frame.rename(
        columns={
            "ticker": "Ticker",
            "pattern": "1H-mønster",
            "setup_type": "Type",
            "score": "Score",
            "entry": "Entry USD",
            "stop": "Stop USD",
            "target": "Target USD",
            "reward_risk": "R/R",
            "position_size_shares": "Antal",
            "position_value_dkk": "Position DKK",
            "risk_dkk": "Risiko DKK",
            "beta": "Beta",
            "return_1w_pct": "1W %",
            "return_1m_pct": "1M %",
            "return_3m_pct": "3M %",
            "relative_strength_3m_pct": "RS 3M %",
            "volume_ratio": "Volumen/20D",
            "failed_filters": "Fejlede filtre",
        }
    )


def render_candidate_detail(item: dict[str, Any]) -> None:
    st.markdown(f"#### {item['ticker']} · {item['pattern']}")
    cols = st.columns(5)
    cols[0].metric("Entry", f"${item['entry']:.2f}")
    cols[1].metric("Stop", f"${item['stop']:.2f}")
    cols[2].metric("Target", f"${item['target']:.2f}")
    cols[3].metric("R/R", f"{item['reward_risk']:.2f}")
    cols[4].metric("Score", f"{item['score']:.1f}")
    risk_cols = st.columns(4)
    risk_cols[0].metric("Antal aktier", f"{item['position_size_shares']}")
    risk_cols[1].metric("Position", f"{item['position_value_dkk']:,.0f} kr.")
    risk_cols[2].metric("Risiko ved stop", f"{item['risk_dkk']:,.0f} kr.")
    risk_cols[3].metric("Beta", f"{item['beta']:.2f}")


def render_history(files: list[Path]) -> None:
    rows: list[dict[str, Any]] = []
    for path in reversed(files):
        try:
            data = load_report(path)
            rows.append(
                {
                    "Dato": path.stem.removeprefix("nasdaq100_swing_"),
                    "Kvalificerede": len(data.get("qualified", [])),
                    "Near-miss": len(data.get("near_miss", [])),
                    "Datafejl": len(data.get("data_failures", [])),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    if rows:
        history = pd.DataFrame(rows).set_index("Dato")
        st.line_chart(history[["Kvalificerede", "Near-miss"]])
        st.dataframe(history, use_container_width=True)
    else:
        st.info("Historikken vises, når der er flere gyldige rapporter.")


st.set_page_config(page_title="Nasdaq-100 Swing Agent", page_icon="📈", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
    [data-testid="stMetric"] {background: rgba(120,120,120,.08); border: 1px solid rgba(120,120,120,.18); padding: .8rem; border-radius: .7rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Nasdaq-100 Swing Agent")
st.caption("Regelbaseret long-screening · 1H teknisk analyse · ikke en købs- eller salgsanbefaling")

files = report_files()
if not files:
    st.warning("Ingen JSON-rapporter fundet i mappen `reports`. Kør GitHub Action-workflowet først.")
    st.stop()
    raise SystemExit(0)

labels = {path.name: path for path in files}
selected_name = st.sidebar.selectbox("Rapport", list(labels), index=0)
selected_path = labels[selected_name]
report = load_report(selected_path)
config = load_config()

qualified = report.get("qualified", [])
near_miss = report.get("near_miss", [])
changes = report.get("changes", {})
failures = report.get("data_failures", [])

st.sidebar.markdown("### Strategiramme")
st.sidebar.write(f"Kapital: **{config.get('account_value_dkk', 0):,.0f} kr.**")
st.sidebar.write(f"Risiko pr. handel: **{config.get('risk_per_trade_pct', 0):.1f}%**")
st.sidebar.write(f"Maks. positioner: **{config.get('max_open_positions', 0)}**")
st.sidebar.caption(f"Genereret: {format_timestamp(report.get('generated_at'))}")

overview = st.columns(5)
overview[0].metric("Kvalificerede", len(qualified))
overview[1].metric("Nye", len(changes.get("new", [])))
overview[2].metric("Udgået", len(changes.get("removed", [])))
overview[3].metric("Near-miss", len(near_miss))
overview[4].metric("Datamangler", len(failures))

tabs = st.tabs(["Kandidater", "Ændringer", "Near-miss", "Historik", "Datakvalitet"])

with tabs[0]:
    st.subheader("Kvalificerede setups")
    if not qualified:
        st.info("Ingen aktier opfyldte alle filtre i denne screening.")
    else:
        max_score = max(float(item.get("score", 0)) for item in qualified)
        min_score = st.slider("Minimum score", 0.0, max(100.0, max_score), 0.0, 1.0)
        setup_types = sorted({str(item.get("setup_type", "Ukendt")) for item in qualified})
        selected_types = st.multiselect("Setup-type", setup_types, default=setup_types)
        filtered = [
            item for item in qualified
            if float(item.get("score", 0)) >= min_score and str(item.get("setup_type", "Ukendt")) in selected_types
        ]
        frame = candidate_frame(filtered)
        visible = [
            "Ticker", "1H-mønster", "Type", "Score", "Entry USD", "Stop USD", "Target USD", "R/R",
            "Antal", "Position DKK", "Risiko DKK", "Beta", "1W %", "1M %", "3M %", "RS 3M %", "Volumen/20D",
        ]
        st.dataframe(frame[[col for col in visible if col in frame]], use_container_width=True, hide_index=True)
        if filtered:
            ticker = st.selectbox("Vis setupdetaljer", [item["ticker"] for item in filtered])
            render_candidate_detail(next(item for item in filtered if item["ticker"] == ticker))

with tabs[1]:
    st.subheader("Ændringer siden seneste screening")
    new = changes.get("new", [])
    removed = changes.get("removed", [])
    col1, col2 = st.columns(2)
    col1.success("Nye kandidater: " + (", ".join(new) if new else "Ingen"))
    col2.warning("Udgåede kandidater: " + (", ".join(removed) if removed else "Ingen"))

with tabs[2]:
    st.subheader("Near-miss · præcis ét manglende filter")
    if not near_miss:
        st.info("Ingen near-miss-kandidater i denne screening.")
    else:
        near_frame = candidate_frame(near_miss)
        near_frame["Manglende kriterium"] = near_frame["Fejlede filtre"].apply(
            lambda values: FILTER_NAMES.get(values[0], values[0]) if isinstance(values, list) and values else "Ukendt"
        )
        visible = ["Ticker", "Manglende kriterium", "1H-mønster", "Type", "Score", "Beta", "1W %", "1M %", "3M %", "RS 3M %", "Volumen/20D"]
        st.dataframe(near_frame[[col for col in visible if col in near_frame]], use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Screeninghistorik")
    render_history(files)

with tabs[4]:
    st.subheader("Datakvalitet")
    if failures:
        st.error(f"Manglende eller utilstrækkelige data for {len(failures)} symboler: {', '.join(sorted(failures))}")
        st.caption("Datamangler må ikke fortolkes som, at aktien ikke har et signal.")
    else:
        st.success("Ingen registrerede datamangler i denne rapport.")
    st.write("Rapportfil:", selected_path.name)
    st.write("Genereret:", format_timestamp(report.get("generated_at")))
