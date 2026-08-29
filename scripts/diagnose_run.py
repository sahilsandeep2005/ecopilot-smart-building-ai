from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import settings
from core.storage import SQLiteStore


def _load_exchange_points() -> dict[str, Any]:
    path = settings.live_dir / "exchange_points_controlled.json"
    if not path.exists():
        path = settings.exchange_points_path
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_diagnostics(store: SQLiteStore | None = None) -> dict[str, Any]:
    store = store or SQLiteStore(settings.db_path)
    baseline = store.all_states("baseline")
    controlled = store.all_states("controlled")
    comparison = store.compare_latest()
    exchange = _load_exchange_points()
    actuators = exchange.get("selected_actuators", {}) if isinstance(exchange, dict) else {}

    actions = store.actions(limit=5000)
    events = store.events(limit=5000)
    real_apply_events = []
    skipped_apply_events = []
    for event in events:
        if event.get("source") != "controlled_runner":
            continue
        payload = event.get("payload") or {}
        runtime = payload.get("runtime_application") or {}
        if runtime.get("applied_values"):
            real_apply_events.append(event)
        elif "Skipped" in str(event.get("message", "")) or (
            "Applied" in str(event.get("message", "")) and runtime.get("reset_to_baseline")
        ):
            skipped_apply_events.append(event)

    controlled_steps = {int(x.get("sim_step", -1)): x for x in controlled}
    baseline_steps = {int(x.get("sim_step", -1)): x for x in baseline}
    common = sorted(set(controlled_steps) & set(baseline_steps))
    demand_diffs = [
        float(baseline_steps[i].get("facility_kw") or 0.0)
        - float(controlled_steps[i].get("facility_kw") or 0.0)
        for i in common
    ]
    lower_demand_steps = sum(1 for value in demand_diffs if value > 0.01)

    active_steps = sum(
        1
        for state in controlled
        if state.get("active_action")
        and not (state.get("active_action") or {}).get("reset_to_baseline")
    )
    occupied_steps = sum(1 for state in controlled if float(state.get("total_occupants") or 0.0) > 0.1)
    max_occupancy = max((float(state.get("total_occupants") or 0.0) for state in controlled), default=0.0)

    actuator_counts = {
        key: len(value or [])
        for key, value in (actuators.items() if isinstance(actuators, dict) else [])
    }
    warnings: list[str] = []
    if not controlled or not baseline:
        warnings.append("Both baseline and controlled telemetry are required before savings can be diagnosed.")
    if max_occupancy <= 0.1 and controlled:
        warnings.append("No occupied period was detected in the controlled run.")
    if sum(actuator_counts.values()) == 0 and controlled:
        warnings.append("No controllable schedule actuators were discovered; control actions cannot affect EnergyPlus.")
    if actuator_counts.get("lighting", 0) == 0:
        warnings.append("No lighting actuator was discovered; one major controllable load is unavailable.")
    if actuator_counts.get("equipment", 0) == 0:
        warnings.append("No electric-equipment actuator was discovered; plug-load savings are unavailable.")
    if active_steps and controlled and active_steps / len(controlled) < 0.50:
        warnings.append("Control coverage is below 50%; actions are active for too few simulation timesteps.")
    if len(real_apply_events) == 0 and actions:
        warnings.append("Actions exist in the database, but no event contains a real actuator write.")
    if comparison.get("ready") and float(comparison.get("energy_saving_pct", 0.0)) <= 0:
        warnings.append("The controlled twin did not reduce aligned cumulative energy in this run.")

    return {
        "comparison": comparison,
        "baseline_states": len(baseline),
        "controlled_states": len(controlled),
        "common_steps": len(common),
        "max_occupancy": max_occupancy,
        "occupied_steps": occupied_steps,
        "active_control_steps": active_steps,
        "control_coverage_pct": (active_steps / len(controlled) * 100.0) if controlled else 0.0,
        "real_actuator_write_events": len(real_apply_events),
        "skipped_or_reset_events": len(skipped_apply_events),
        "actuator_counts": actuator_counts,
        "steps_with_lower_controlled_demand": lower_demand_steps,
        "max_instantaneous_demand_reduction_kw": max(demand_diffs, default=0.0),
        "average_demand_reduction_kw": (sum(demand_diffs) / len(demand_diffs)) if demand_diffs else 0.0,
        "warnings": warnings,
    }


def main() -> int:
    diagnostics = build_diagnostics()
    output = settings.project_root / "data" / "diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")

    comparison = diagnostics.get("comparison", {})
    print("\nEcoPilot run diagnostics")
    print("=" * 60)
    if comparison.get("ready"):
        print(f"Aligned step: {comparison.get('aligned_step')}")
        print(f"Baseline energy:   {comparison.get('baseline_cumulative_kwh', 0):.3f} kWh")
        print(f"Controlled energy: {comparison.get('controlled_cumulative_kwh', 0):.3f} kWh")
        print(f"Energy saving:     {comparison.get('energy_saving_pct', 0):.3f}%")
        print(f"Peak reduction:    {comparison.get('peak_reduction_pct', 0):.3f}%")
    else:
        print("Aligned twin comparison is not ready.")
    print(f"Control coverage:  {diagnostics['control_coverage_pct']:.1f}%")
    print(f"Real actuator writes: {diagnostics['real_actuator_write_events']}")
    print(f"Actuator counts: {diagnostics['actuator_counts']}")
    print(f"Steps with lower EcoPilot demand: {diagnostics['steps_with_lower_controlled_demand']}")
    if diagnostics["warnings"]:
        print("\nWarnings / likely causes:")
        for warning in diagnostics["warnings"]:
            print(f"- {warning}")
    else:
        print("\nNo obvious integration issue was detected.")
    print(f"\nDetailed JSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
