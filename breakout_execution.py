from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from breakout_runner import _usd_dkk, load_journal
from swing_agent import load_config


@dataclass(frozen=True)
class ContractSpec:
    code: str
    label: str
    point_value_usd: float
    tick_size: float

    @property
    def tick_value_usd(self) -> float:
        return self.point_value_usd * self.tick_size


@dataclass(frozen=True)
class Feasibility:
    contract: str
    stop_distance_points: float
    point_value_usd: float
    tick_size: float
    tick_value_usd: float
    risk_per_contract_usd: float
    risk_per_contract_dkk: float
    risk_budget_dkk: float
    max_contracts_by_risk: int
    feasible: bool
    notional_usd_per_contract: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_contracts(execution_cfg: dict[str, Any]) -> list[ContractSpec]:
    contracts: list[ContractSpec] = []
    for code, raw in execution_cfg.get("contracts", {}).items():
        if raw.get("enabled", True) is False:
            continue
        contracts.append(
            ContractSpec(
                code=code,
                label=str(raw.get("label", code)),
                point_value_usd=float(raw["point_value_usd"]),
                tick_size=float(raw["tick_size"]),
            )
        )
    return contracts


def assess_signal(
    signal: dict[str, Any],
    contract: ContractSpec,
    usd_dkk: float,
    risk_budget_dkk: float,
    max_contracts: int | None = None,
) -> Feasibility:
    entry = float(signal["entry"])
    stop = float(signal["stop"])
    distance = abs(entry - stop)
    risk_usd = distance * contract.point_value_usd
    risk_dkk = risk_usd * usd_dkk
    allowed = math.floor(risk_budget_dkk / risk_dkk) if risk_dkk > 0 else 0
    if max_contracts is not None:
        allowed = min(allowed, max_contracts)
    return Feasibility(
        contract=contract.code,
        stop_distance_points=round(distance, 3),
        point_value_usd=contract.point_value_usd,
        tick_size=contract.tick_size,
        tick_value_usd=round(contract.tick_value_usd, 4),
        risk_per_contract_usd=round(risk_usd, 2),
        risk_per_contract_dkk=round(risk_dkk, 2),
        risk_budget_dkk=round(risk_budget_dkk, 2),
        max_contracts_by_risk=max(0, allowed),
        feasible=allowed >= 1,
        notional_usd_per_contract=round(entry * contract.point_value_usd, 2),
    )


def summarize_journal(
    rows: list[dict[str, Any]],
    contract: ContractSpec,
    usd_dkk: float,
    risk_budget_dkk: float,
    max_contracts: int | None = None,
) -> dict[str, Any]:
    usable = [row for row in rows if row.get("entry") is not None and row.get("stop") is not None]
    assessments = [assess_signal(row, contract, usd_dkk, risk_budget_dkk, max_contracts) for row in usable]
    feasible = [item for item in assessments if item.feasible]
    risks = [item.risk_per_contract_dkk for item in assessments]
    return {
        "signals": len(assessments),
        "feasible_signals": len(feasible),
        "feasibility_pct": round(len(feasible) / len(assessments) * 100, 1) if assessments else None,
        "median_risk_per_contract_dkk": round(sorted(risks)[len(risks) // 2], 2) if risks else None,
        "latest": assessments[-1].to_dict() if assessments else None,
    }


def run(config_path: Path) -> Path:
    cfg = load_config(config_path)
    strategy = cfg["asian_breakout"]
    execution = strategy.get("execution", {})
    contracts = load_contracts(execution)
    if not contracts:
        raise RuntimeError("No execution contracts configured")

    usd_dkk = _usd_dkk(cfg)
    risk_pct = float(execution.get("risk_budget_pct", strategy.get("risk_per_trade_pct", 1.0)))
    risk_budget_dkk = float(cfg["account_value_dkk"]) * risk_pct / 100
    max_contracts = execution.get("max_contracts")
    if max_contracts is not None:
        max_contracts = int(max_contracts)

    root = config_path.parent
    profile_names = list(strategy.get("validation", {}).get("profiles", {}).keys()) or ["control", "challenger"]
    profiles: dict[str, Any] = {}
    for name in profile_names:
        rows = load_journal(root / "state" / f"asian_breakout_{name}_journal.json")
        profiles[name] = {
            contract.code: summarize_journal(rows, contract, usd_dkk, risk_budget_dkk, max_contracts)
            for contract in contracts
        }

    latest_profile_path = root / "reports" / "asian_breakout_profiles_latest.json"
    latest_profiles: dict[str, Any] = {}
    if latest_profile_path.exists():
        try:
            latest_profiles = json.loads(latest_profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            latest_profiles = {}

    latest_signals: dict[str, Any] = {}
    for name, profile in latest_profiles.get("profiles", {}).items():
        signal = profile.get("signal")
        if not signal:
            continue
        latest_signals[name] = {
            contract.code: assess_signal(signal, contract, usd_dkk, risk_budget_dkk, max_contracts).to_dict()
            for contract in contracts
        }

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "pre_cost_execution_feasibility",
        "source_signal": strategy.get("ticker", "NQ=F"),
        "usd_dkk": round(usd_dkk, 4),
        "risk_budget_dkk": round(risk_budget_dkk, 2),
        "risk_budget_pct": risk_pct,
        "contracts": {contract.code: asdict(contract) | {"tick_value_usd": contract.tick_value_usd} for contract in contracts},
        "profiles": profiles,
        "latest_signals": latest_signals,
        "warning": (
            "This is a distance-based pre-cost feasibility model. It uses NQ=F signal point distances and does not assume "
            "broker availability, margin approval, commissions, slippage, or identical executable prices in MNQ/NNQ. "
            "Use an actual target-contract feed and broker cost schedule before live trading."
        ),
    }
    output = root / "reports" / "asian_breakout_execution_latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess Asian breakout futures execution feasibility")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()
    print(run(args.config).resolve())


if __name__ == "__main__":
    main()
