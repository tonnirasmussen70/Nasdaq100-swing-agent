from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from asian_breakout import evaluate_breakout
from breakout_runner import append_signal, download_intraday, load_journal, performance, resolve_open_trades
from swing_agent import load_config


def build_profile(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    profile = dict(base)
    profile.update(overrides)
    return profile


def run_profile(
    name: str,
    frame,
    strategy: dict[str, Any],
    account_value_dkk: float,
    root: Path,
) -> dict[str, Any]:
    cfg = dict(strategy)
    cfg["account_value_dkk"] = account_value_dkk
    journal_path = root / "state" / f"asian_breakout_{name}_journal.json"
    resolved = resolve_open_trades(journal_path, frame)
    signal = evaluate_breakout(strategy["ticker"], frame, cfg, usd_dkk=1.0)
    added = append_signal(journal_path, signal) if signal else False
    rows = load_journal(journal_path)
    return {
        "profile": name,
        "settings": {
            "max_asian_range_pct": strategy["max_asian_range_pct"],
            "min_body_ratio": strategy["min_body_ratio"],
            "reward_risk": strategy["reward_risk"],
        },
        "signal": signal.to_dict() if signal else None,
        "new_signal": added,
        "resolved_trades": resolved,
        "performance": performance(rows),
        "journal_file": str(journal_path),
    }


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    base = dict(cfg["asian_breakout"])
    validation = base.get("validation", {})
    profiles = validation.get("profiles", {})
    if not profiles:
        raise RuntimeError("No validation profiles configured")

    frame = download_intraday(base["ticker"], base["data_period"], base["data_interval"])
    results = {}
    for name, overrides in profiles.items():
        strategy = build_profile(base, overrides)
        results[name] = run_profile(name, frame, strategy, cfg["account_value_dkk"], config_path.parent)

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "ticker": base["ticker"],
        "mode": "prospective_paper_comparison",
        "promotion_rule": validation.get(
            "promotion_rule",
            "Do not promote challenger until a sufficient prospective sample exists and performance remains superior after costs.",
        ),
        "profiles": results,
    }
    output = config_path.parent / "reports" / "asian_breakout_profiles_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Prospective control/challenger breakout paper comparison")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
