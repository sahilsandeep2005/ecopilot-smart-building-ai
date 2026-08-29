from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.config import settings
from core.storage import SQLiteStore
from core.health import summarize_system_health
from core.utils import write_json


def _compliance(states: list[dict[str, Any]]) -> tuple[float, float | None, int, int, int, int]:
    comfort_ok = 0
    comfort_total = 0
    co2_ok = 0
    co2_total = 0
    for state in states:
        for zone in state.get("zones", []):
            if not zone.get("occupied"):
                continue
            temperature = zone.get("temperature_c")
            pmv = zone.get("pmv")
            if temperature is not None:
                comfort_total += 1
                temperature_ok = settings.occupied_temp_min_c <= float(temperature) <= settings.occupied_temp_max_c
                pmv_ok = pmv is None or abs(float(pmv)) <= settings.max_abs_pmv
                if temperature_ok and pmv_ok:
                    comfort_ok += 1
            co2 = zone.get("co2_ppm")
            if co2 is not None:
                co2_total += 1
                if float(co2) <= settings.max_co2_ppm:
                    co2_ok += 1
    comfort_pct = comfort_ok / comfort_total * 100.0 if comfort_total else 100.0
    co2_pct = co2_ok / co2_total * 100.0 if co2_total else None
    return comfort_pct, co2_pct, comfort_ok, comfort_total, co2_ok, co2_total


def calculate_metrics(store: SQLiteStore | None = None) -> dict[str, Any]:
    store = store or SQLiteStore(settings.db_path)
    baseline = store.all_states("baseline")
    controlled = store.all_states("controlled")
    latest_comparison = store.compare_latest()
    comfort_pct, co2_pct, comfort_ok, comfort_total, co2_ok, co2_total = _compliance(controlled)
    actions = store.actions(limit=5000)
    applied = sum(1 for action in actions if action.get("status") in {"applied", "completed"})
    rejected = sum(1 for action in actions if action.get("status") == "rejected")
    skipped = sum(1 for action in actions if action.get("status") == "skipped")

    all_events = store.events(limit=5000)
    health = summarize_system_health(all_events)

    return {
        "ready": bool(baseline and controlled and latest_comparison.get("ready")),
        "baseline_state_count": len(baseline),
        "controlled_state_count": len(controlled),
        "aligned_step": latest_comparison.get("aligned_step"),
        "baseline_energy_kwh": latest_comparison.get("baseline_cumulative_kwh", 0.0),
        "controlled_energy_kwh": latest_comparison.get("controlled_cumulative_kwh", 0.0),
        "energy_saving_pct": latest_comparison.get("energy_saving_pct", 0.0),
        "baseline_peak_kw": latest_comparison.get("baseline_peak_kw", 0.0),
        "controlled_peak_kw": latest_comparison.get("controlled_peak_kw", 0.0),
        "peak_reduction_pct": latest_comparison.get("peak_reduction_pct", 0.0),
        "baseline_hvac_kwh": latest_comparison.get("baseline_hvac_kwh"),
        "controlled_hvac_kwh": latest_comparison.get("controlled_hvac_kwh"),
        "hvac_energy_saving_pct": latest_comparison.get("hvac_energy_saving_pct"),
        "comfort_compliance_pct": comfort_pct,
        "co2_compliance_pct": co2_pct,
        "comfort_compliant_observations": comfort_ok,
        "comfort_observations": comfort_total,
        "co2_compliant_observations": co2_ok,
        "co2_observations": co2_total,
        "applied_actions": applied,
        "rejected_actions": rejected,
        "skipped_actions": skipped,
        "warning_events": health["warning_events"],
        "error_events": health["recoverable_diagnostics"],
        "critical_events": health["critical_events"],
        "runtime_failures": health["runtime_failures"],
        "energyplus_severe_events": health["energyplus_severe_events"],
        "agent_error_events": health["agent_error_events"],
        "control_error_events": health["control_error_events"],
        "recoverable_diagnostics": health["recoverable_diagnostics"],
        "safety_interventions": health["safety_interventions"],
        "system_health_status": health["status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare EcoPilot baseline and controlled runs.")
    parser.add_argument("--output", type=Path, default=settings.project_root / "data" / "metrics.json")
    args = parser.parse_args()
    metrics = calculate_metrics()
    write_json(args.output, metrics)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
