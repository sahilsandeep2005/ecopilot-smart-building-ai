from agent.schemas import BuildingState, ZoneState
from control.optimizer import ControlOptimizer


def test_optimizer_returns_candidate():
    state = BuildingState(
        run_id="test",
        mode="controlled",
        sim_step=20,
        sim_time_hours=5.0,
        timestamp_utc="2026-01-01T00:00:00+00:00",
        calendar={"hour": 10},
        outdoor_temperature_c=30,
        facility_kw=80,
        peak_kw=90,
        total_occupants=10,
        zones=[
            ZoneState(
                name="Zone 1",
                temperature_c=24,
                pmv=0.2,
                co2_ppm=750,
                occupants=10,
                occupied=True,
            )
        ],
    )
    result = ControlOptimizer().optimize(state)
    assert result.selected_action.reason
    assert result.candidates
    assert result.candidates[0].total_score <= result.candidates[-1].total_score


def test_optimizer_uses_real_unoccupied_setback():
    state = BuildingState(
        run_id="test",
        mode="controlled",
        sim_step=30,
        sim_time_hours=7.5,
        timestamp_utc="2026-07-15T00:00:00+00:00",
        calendar={"hour": 2},
        outdoor_temperature_c=28,
        facility_kw=12,
        peak_kw=20,
        total_occupants=0,
        available_signals=[
            "cooling_schedule_actuators",
            "heating_schedule_actuators",
            "lighting_schedule_actuators",
            "equipment_schedule_actuators",
            "ventilation_schedule_actuators",
        ],
        zones=[ZoneState(name="Zone 1", temperature_c=24, occupants=0, occupied=False)],
    )
    result = ControlOptimizer().optimize(state)
    action = result.selected_action
    assert action.mode == "UNOCCUPIED_SETBACK"
    assert action.force_when_unoccupied is True
    assert action.reset_to_baseline is False
    assert action.lighting_fraction is not None and action.lighting_fraction <= 0.2
    assert action.equipment_fraction is not None and action.equipment_fraction <= 0.35


def test_unoccupied_setback_increases_ventilation_for_high_residual_co2():
    state = BuildingState(
        run_id="test",
        mode="controlled",
        sim_step=31,
        sim_time_hours=7.75,
        timestamp_utc="2026-07-15T00:00:00+00:00",
        calendar={"hour": 19},
        outdoor_temperature_c=28,
        facility_kw=12,
        peak_kw=20,
        total_occupants=0,
        available_signals=[
            "cooling_schedule_actuators",
            "heating_schedule_actuators",
            "lighting_schedule_actuators",
            "equipment_schedule_actuators",
            "ventilation_schedule_actuators",
        ],
        zones=[
            ZoneState(
                name="Zone 1",
                temperature_c=24,
                co2_ppm=980,
                occupants=0,
                occupied=False,
            )
        ],
    )
    action = ControlOptimizer().optimize(state).selected_action
    assert action.mode == "UNOCCUPIED_SETBACK"
    assert action.ventilation_fraction == 0.60
    assert "Residual CO2 is high" in action.reason


def test_unoccupied_setback_uses_moderate_ventilation_for_elevated_residual_co2():
    state = BuildingState(
        run_id="test",
        mode="controlled",
        sim_step=32,
        sim_time_hours=8.0,
        timestamp_utc="2026-07-15T00:00:00+00:00",
        calendar={"hour": 20},
        outdoor_temperature_c=28,
        facility_kw=12,
        peak_kw=20,
        total_occupants=0,
        available_signals=["ventilation_schedule_actuators"],
        zones=[
            ZoneState(
                name="Zone 1",
                temperature_c=24,
                co2_ppm=820,
                occupants=0,
                occupied=False,
            )
        ],
    )
    action = ControlOptimizer().optimize(state).selected_action
    assert action.ventilation_fraction == 0.35


def test_occupied_high_co2_forces_iaq_recovery_when_ventilation_is_available():
    state = BuildingState(
        run_id="test",
        mode="controlled",
        sim_step=40,
        sim_time_hours=10.0,
        timestamp_utc="2026-07-15T00:00:00+00:00",
        calendar={"hour": 14},
        outdoor_temperature_c=34,
        facility_kw=40,
        peak_kw=45,
        total_occupants=10,
        available_signals=[
            "cooling_schedule_actuators",
            "heating_schedule_actuators",
            "lighting_schedule_actuators",
            "equipment_schedule_actuators",
            "ventilation_schedule_actuators",
        ],
        zones=[
            ZoneState(
                name="Zone 1",
                temperature_c=24.0,
                co2_ppm=920,
                occupants=10,
                occupied=True,
            )
        ],
    )
    action = ControlOptimizer().optimize(state).selected_action
    assert action.mode == "IAQ_RECOVERY"
    assert action.ventilation_fraction is not None
    assert action.ventilation_fraction >= 1.0
    assert action.hold_steps == 4
