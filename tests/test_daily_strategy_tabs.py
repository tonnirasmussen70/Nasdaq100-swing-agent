from pathlib import Path

def test_strategy_tabs_are_mapped():
    src=Path("app.py").read_text(encoding="utf-8")
    assert 'with tabs[1]:\n    st.subheader("Trend + Momentum Pullback")' in src
    assert 'with tabs[2]:\n    st.subheader("Volatility Breakout + Relative Strength")' in src
    assert 'with tabs[3]:\n    st.subheader("Asian / London Breakout · paper trading")' in src
    assert 'with tabs[4]:\n    st.subheader("Ændringer siden seneste screening")' in src
    assert 'with tabs[5]:\n    st.subheader("Near-miss · præcis ét manglende filter")' in src
    assert 'with tabs[6]:\n    st.subheader("Screeninghistorik")' in src
    assert 'with tabs[7]:\n    st.subheader("Datakvalitet")' in src

# CI refresh: validate corrected PR 13 tab mapping.
