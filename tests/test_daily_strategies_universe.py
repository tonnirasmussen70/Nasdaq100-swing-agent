from pathlib import Path

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
