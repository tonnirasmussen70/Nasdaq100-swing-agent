from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from breakout_runner import load_journal, performance
from swing_agent import load_config


def _cost_adjusted_rows(rows: list[dict[str, Any]], cost_r: float) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if copy.get("status") == "CLOSED" and copy.get("result_r") is not None:
            copy["result_r"] = float(copy["result_r"]) - float(cost_r)
        adjusted.append(copy)
    return adjusted


def cost_sensitivity(
    control_rows: list[dict[str, Any]],
    challenger_rows: list[dict[str, Any]],
    costs_r: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cost_r in costs_r:
        control = performance(_cost_adjusted_rows(control_rows, cost_r))
        challenger = performance(_cost_adjusted_rows(challenger_rows, cost_r))
        rows.append(
            {
                "cost_r_per_trade": float(cost_r),
                "control": control,
                "challenger": challenger,
                "challenger_positive": (challenger.get("expectancy_r") or 0) > 0
                and (challenger.get("profit_factor") or 0) > 1,
            }
        )
    return rows


def validation_status(
    control_rows: list[dict[str, Any]],
    challenger_rows: list[dict[str, Any]],
    minimum_closed_trades: int,
    costs_r: list[float] | None = None,
) -> dict[str, Any]:
    control = performance(control_rows)
    challenger = performance(challenger_rows)
    control_closed = int(control.get("closed_trades", 0) or 0)
    challenger_closed = int(challenger.get("closed_trades", 0) or 0)
    progress_pct = min(100.0, challenger_closed / max(1, minimum_closed_trades) * 100)

    reasons: list[str] = []
    if challenger_closed < minimum_closed_trades:
        reasons.append(f"Need {minimum_closed_trades - challenger_closed} more closed challenger trades")
    if challenger_closed >= minimum_closed_trades:
        if (challenger.get("expectancy_r") or 0) <= 0:
            reasons.append("Challenger expectancy is not positive")
        if (challenger.get("profit_factor") or 0) <= 1:
            reasons.append("Challenger profit factor is not above 1")
        challenger_dd = challenger.get("max_drawdown_r")
        control_dd = control.get("max_drawdown_r")
        if challenger_dd is not None and control_dd is not None and challenger_dd > control_dd:
            reasons.append("Challenger max drawdown is worse than control")

    quantitative_gate = (
        challenger_closed >= minimum_closed_trades
        and (challenger.get("expectancy_r") or 0) > 0
        and (challenger.get("profit_factor") or 0) > 1
        and (
            control.get("max_drawdown_r") is None
            or challenger.get("max_drawdown_r") is None
            or challenger["max_drawdown_r"] <= control["max_drawdown_r"]
        )
    )

    stress = cost_sensitivity(control_rows, challenger_rows, costs_r or [0.0])
    positive_scenarios = [row["cost_r_per_trade"] for row in stress if row["challenger_positive"]]
    max_positive_cost_r = max(positive_scenarios) if positive_scenarios else None

    status = "REVIEW_REQUIRED" if quantitative_gate else "COLLECTING_DATA"
    return {
        "status": status,
        "quantitative_gate_passed": quantitative_gate,
        "automatic_promotion": False,
        "costs_included_in_gate": False,
        "minimum_closed_trades": minimum_closed_trades,
        "challenger_closed_trades": challenger_closed,
        "control_closed_trades": control_closed,
        "progress_pct": round(progress_pct, 1),
        "reasons": reasons,
        "control": control,
        "challenger": challenger,
        "cost_sensitivity": stress,
        "max_tested_cost_r_with_positive_challenger": max_positive_cost_r,
        "note": (
            "REVIEW_REQUIRED is not an automatic promotion. Cost scenarios are stress tests in R, "
            "not broker-specific fee estimates. Realistic MNQ fees/slippage and a human review are "
            "still required before any strategy change."
        ),
    }


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    validation = cfg["asian_breakout"].get("validation", {})
    minimum = int(validation.get("minimum_prospective_closed_trades", 30))
    costs_r = [float(value) for value in validation.get("cost_stress_r_per_trade", [0.0])]
    root = config_path.parent
    control_path = root / "state" / "asian_breakout_control_journal.json"
    challenger_path = root / "state" / "asian_breakout_challenger_journal.json"
    payload = validation_status(
        load_journal(control_path),
        load_journal(challenger_path),
        minimum,
        costs_r=costs_r,
    )
    payload["generated_at"] = datetime.now().astimezone().isoformat()
    payload["promotion_rule"] = validation.get("promotion_rule")
    output = root / "reports" / "asian_breakout_validation_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate prospective Asian breakout control/challenger gate")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
