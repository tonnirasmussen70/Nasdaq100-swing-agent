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


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Ukendt"
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone().strftime("%d-%m-%Y kl. %H:%M %Z")
    except ValueError:
        return value


def format_number(value: Any, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


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


def render_profile(name: str, profile: dict[str, Any]) -> None:
    settings = profile.get("settings", {})
    perf = profile.get("performance", {})
    st.markdown(f"#### {name.title()}")
    st.caption(
        f"Asian range ≤ {settings.get('max_asian_range_pct', '—')}% · "
        f"body ≥ {float(settings.get('min_body_ratio', 0)) * 100:.0f}% · "
        f"target {settings.get('reward_risk', '—')}R"
    )
    cols = st.columns(4)
    cols[0].metric("Lukkede", perf.get("closed_trades", 0))
    cols[1].metric("Expectancy", format_number(perf.get("expectancy_r"), "R"))
    cols[2].metric("Profit factor", format_number(perf.get("profit_factor")))
    cols[3].metric("Max DD", format_number(perf.get("max_drawdown_r"), "R"))
    signal = profile.get("signal")
    if signal:
        st.success(
            f"{signal['side']} · entry ${signal['entry']:.2f} · "
            f"stop ${signal['stop']:.2f} · target ${signal['target']:.2f}"
        )
    else:
        st.caption("Intet nyt signal i seneste kørsel.")


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
st.caption("Regelbaseret screening og paper-validering · ingen automatisk live execution")

config = load_config()
files = report_files()
selected_path: Path | None = None
report: dict[str, Any] = {}
if files:
    labels = {path.name: path for path in files}
    selected_name = st.sidebar.selectbox("Rapport", list(labels), index=0)
    selected_path = labels[selected_name]
    report = load_report(selected_path)
else:
    st.sidebar.info("Ingen swing-rapport endnu. Breakout-valideringen kan stadig vises.")

qualified = report.get("qualified", [])
near_miss = report.get("near_miss", [])
changes = report.get("changes", {})
failures = report.get("data_failures", [])

st.sidebar.markdown("### Strategiramme")
st.sidebar.write(f"Kapital: **{config.get('account_value_dkk', 0):,.0f} kr.**")
st.sidebar.write(f"Risiko pr. swing-handel: **{config.get('risk_per_trade_pct', 0):.1f}%**")
st.sidebar.write(f"Maks. positioner: **{config.get('max_open_positions', 0)}**")
if report:
    st.sidebar.caption(f"Swing-rapport: {format_timestamp(report.get('generated_at'))}")

overview = st.columns(5)
overview[0].metric("Kvalificerede", len(qualified))
overview[1].metric("Nye", len(changes.get("new", [])))
overview[2].metric("Udgået", len(changes.get("removed", [])))
overview[3].metric("Near-miss", len(near_miss))
overview[4].metric("Datamangler", len(failures))

tabs = st.tabs(["Kandidater", "Asian Breakout", "Ændringer", "Near-miss", "Historik", "Datakvalitet"])

with tabs[0]:
    st.subheader("Kvalificerede setups")
    if not qualified:
        st.info("Ingen aktier opfyldte alle filtre i denne screening, eller der er endnu ingen swing-rapport.")
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
    st.subheader("Asian / London Breakout · paper trading")
    breakout_path = ROOT / "reports" / "asian_breakout_latest.json"
    journal_path = ROOT / "state" / "asian_breakout_journal.json"
    breakout = load_optional_json(breakout_path)
    if not breakout:
        st.info("Ingen aktiv breakout-rapport endnu. Monitoren opretter den ved næste gyldige kørsel.")
    else:
        perf = breakout.get("performance", {})
        metrics = st.columns(5)
        metrics[0].metric("Lukkede handler", perf.get("closed_trades", 0))
        metrics[1].metric("Win-rate", format_number(perf.get("win_rate_pct"), "%", 1))
        metrics[2].metric("Expectancy", format_number(perf.get("expectancy_r"), "R"))
        metrics[3].metric("Profit factor", format_number(perf.get("profit_factor")))
        metrics[4].metric("Max drawdown", format_number(perf.get("max_drawdown_r"), "R"))
        signal = breakout.get("signal")
        if signal:
            st.success(f"{signal['side']} signal · {signal['ticker']} · entry ${signal['entry']:.2f} · stop ${signal['stop']:.2f} · target ${signal['target']:.2f}")
        else:
            st.caption("Seneste kørsel gav intet nyt breakout-signal.")

    st.divider()
    st.markdown("### Prospective control vs. challenger")
    profiles = load_optional_json(ROOT / "reports" / "asian_breakout_profiles_latest.json")
    validation = load_optional_json(ROOT / "reports" / "asian_breakout_validation_latest.json")
    if not profiles:
        st.info("Prospective journaler starter ved næste paper-monitor kørsel på main.")
    else:
        left, right = st.columns(2)
        with left:
            render_profile("control", profiles.get("profiles", {}).get("control", {}))
        with right:
            render_profile("challenger", profiles.get("profiles", {}).get("challenger", {}))

    if validation:
        st.markdown("#### Promotion gate")
        gate_cols = st.columns(4)
        gate_cols[0].metric("Status", validation.get("status", "COLLECTING_DATA"))
        gate_cols[1].metric("Challenger handler", f"{validation.get('challenger_closed_trades', 0)}/{validation.get('minimum_closed_trades', 30)}")
        gate_cols[2].metric("Progress", f"{validation.get('progress_pct', 0):.1f}%")
        gate_cols[3].metric("Automatisk promotion", "Nej")
        st.progress(min(1.0, max(0.0, float(validation.get("progress_pct", 0)) / 100)))
        reasons = validation.get("reasons", [])
        if reasons:
            st.caption(" · ".join(reasons))
        st.warning("Gate-status kan kun udløse REVIEW_REQUIRED. Strategien ændres ikke automatisk, og costs/slippage skal vurderes før en eventuel promotion.")

    if journal_path.exists():
        journal = load_optional_json(journal_path)
        if isinstance(journal, list) and journal:
            with st.expander("Aktiv paper-journal"):
                st.dataframe(pd.DataFrame(journal), use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Ændringer siden seneste screening")
    new = changes.get("new", [])
    removed = changes.get("removed", [])
    col1, col2 = st.columns(2)
    col1.success("Nye kandidater: " + (", ".join(new) if new else "Ingen"))
    col2.warning("Udgåede kandidater: " + (", ".join(removed) if removed else "Ingen"))

with tabs[3]:
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

with tabs[4]:
    st.subheader("Screeninghistorik")
    render_history(files)

with tabs[5]:
    st.subheader("Datakvalitet")
    if not selected_path:
        st.info("Ingen swing-rapport er tilgængelig endnu.")
    elif failures:
        st.error(f"Manglende eller utilstrækkelige data for {len(failures)} symboler: {', '.join(sorted(failures))}")
        st.caption("Datamangler må ikke fortolkes som, at aktien ikke har et signal.")
    else:
        st.success("Ingen registrerede datamangler i denne rapport.")
    if selected_path:
        st.write("Rapportfil:", selected_path.name)
        st.write("Genereret:", format_timestamp(report.get("generated_at")))
