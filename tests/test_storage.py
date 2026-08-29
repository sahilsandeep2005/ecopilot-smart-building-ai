from pathlib import Path

from core.storage import SQLiteStore


def test_state_and_action_roundtrip(tmp_path: Path):
    store = SQLiteStore(tmp_path / "test.db")
    state = {
        "run_id": "r1",
        "mode": "controlled",
        "sim_step": 1,
        "sim_time_hours": 0.25,
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "facility_kw": 10,
        "cumulative_kwh": 2,
        "peak_kw": 10,
        "zones": [],
    }
    store.insert_state(state)
    assert store.latest_state("controlled")["sim_step"] == 1
    action = {
        "action_id": "a1",
        "created_for_step": 1,
        "source": "test",
        "mode": "NORMAL",
        "reason": "Test action",
    }
    row = store.insert_action(action, "token")
    assert row["payload"]["action_id"] == "a1"
    assert store.next_approved_action(0)["id"] == row["id"]


def test_compare_latest_aligns_by_simulation_step(tmp_path: Path):
    store = SQLiteStore(tmp_path / "aligned.db")
    base_common = {
        "run_id": "b1", "mode": "baseline", "sim_step": 4, "sim_time_hours": 1.0,
        "timestamp_utc": "2026-07-15T00:00:00+00:00", "facility_kw": 10.0,
        "cumulative_kwh": 10.0, "peak_kw": 10.0, "hvac_kwh": 5.0, "zones": [],
    }
    ctrl_common = {
        "run_id": "c1", "mode": "controlled", "sim_step": 4, "sim_time_hours": 1.0,
        "timestamp_utc": "2026-07-15T00:00:00+00:00", "facility_kw": 9.0,
        "cumulative_kwh": 9.0, "peak_kw": 9.0, "hvac_kwh": 4.0, "zones": [],
    }
    store.insert_state(base_common)
    store.insert_state(ctrl_common)
    # Baseline gets ahead. A naive latest/latest comparison would be wrong.
    ahead = dict(base_common)
    ahead.update(sim_step=5, sim_time_hours=1.25, cumulative_kwh=13.0, facility_kw=12.0, peak_kw=12.0)
    store.insert_state(ahead)
    comparison = store.compare_latest()
    assert comparison["aligned_step"] == 4
    assert round(comparison["energy_saving_pct"], 6) == 10.0
    assert round(comparison["hvac_energy_saving_pct"], 6) == 20.0
