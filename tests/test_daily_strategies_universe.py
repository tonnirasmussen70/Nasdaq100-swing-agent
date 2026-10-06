import json
from pathlib import Path

import numpy as np
import pandas as pd

import daily_strategies


def test_universe_uses_bundled_symbols_without_http(monkeypatch):
    symbols_file = Path(__file__).resolve().parents[1] / "nasdaq100_symbols.txt"
    expected = [
        line.strip()
        for line in symbols_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    def reject_http(*args, **kwargs):
        raise AssertionError("universe() must not fetch Wikipedia over HTTP")

    monkeypatch.setattr(daily_strategies.pd, "read_html", reject_http)

    assert daily_strategies.universe() == expected
    assert expected
    assert len(expected) == len(set(expected))


def test_main_writes_report_with_strategy_signals(monkeypatch, tmp_path):
    pullback_signal = {
        "ticker": "AAPL",
        "entry": 200.0,
        "return_3m_pct": 5.0,
        "rsi14": 60.0,
    }
    breakout_signal = {
        "ticker": "MSFT",
        "entry": 400.0,
        "rs_vs_ndx_3m_pct": 4.0,
        "volume_ratio": 2.0,
    }
    monkeypatch.setattr(daily_strategies, "universe", lambda: ["AAPL", "MSFT"])
    monkeypatch.setattr(
        daily_strategies,
        "one",
        lambda ticker, ndx_return: (
            pullback_signal if ticker == "AAPL" else None,
            breakout_signal if ticker == "MSFT" else None,
        ),
    )
    monkeypatch.setattr(
        daily_strategies.yf,
        "download",
        lambda *args, **kwargs: pd.DataFrame(
            {"Close": np.linspace(100.0, 110.0, 64)}
        ),
    )
    monkeypatch.setattr(
        daily_strategies,
        "OUT",
        tmp_path / "reports" / "daily_strategies_latest.json",
    )

    daily_strategies.main()

    report = json.loads(
        (tmp_path / "reports" / "daily_strategies_latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["mode"] == "paper_observation"
    assert report["pullback"] == [pullback_signal]
    assert report["breakout"] == [breakout_signal]
    assert report["data_failures"] == []
