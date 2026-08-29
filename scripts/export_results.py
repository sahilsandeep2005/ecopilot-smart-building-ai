from __future__ import annotations

import csv
import json
from pathlib import Path

from core.config import settings
from core.storage import SQLiteStore
from experiments.compare_runs import calculate_metrics


def _write_timeseries(path: Path, states: list[dict]) -> None:
    fields = [
        "sim_step",
        "sim_time_hours",
        "facility_kw",
        "cumulative_kwh",
        "peak_kw",
        "hvac_kwh",
        "total_occupants",
        "outdoor_temperature_c",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for state in states:
            writer.writerow({name: state.get(name) for name in fields})


def main() -> int:
    store = SQLiteStore(settings.db_path)
    results = settings.project_root / "results"
    results.mkdir(parents=True, exist_ok=True)
    metrics = calculate_metrics(store)
    (results / "final_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    _write_timeseries(results / "baseline_timeseries.csv", store.all_states("baseline"))
    _write_timeseries(results / "controlled_timeseries.csv", store.all_states("controlled"))

    with (results / "runtime_actions.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["id", "status", "created_for_step", "applied_step", "source", "mode", "reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in reversed(store.actions(limit=5000)):
            payload = row.get("payload") or {}
            writer.writerow(
                {
                    "id": row.get("id"),
                    "status": row.get("status"),
                    "created_for_step": row.get("created_for_step"),
                    "applied_step": row.get("applied_step"),
                    "source": row.get("source"),
                    "mode": payload.get("mode"),
                    "reason": payload.get("reason"),
                }
            )
    print(f"Results exported to {results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
