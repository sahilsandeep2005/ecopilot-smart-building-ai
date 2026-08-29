from __future__ import annotations

from pathlib import Path

from agent.schemas import (
    BuildingState,
    ControlAction,
    OptimizationCandidate,
    OptimizationResult,
)
from control.constraints import ConstraintChecker
from control.fallback_controller import safe_fallback_action
from control.surrogate import SurrogateModel
from core.config import settings


class ControlOptimizer:
    """Safety-first candidate optimizer.

    Three profiles are available:
    - conservative: smallest interventions
    - balanced: default competition profile
    - demo: stronger but still bounded short-run PoC controls

    The profile changes *candidate actions*, never the safety constraints.
    """

    def __init__(self, surrogate_path: Path | str | None = None):
        self.surrogate = SurrogateModel(surrogate_path)
        self.constraints = ConstraintChecker()

    @staticmethod
    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    @staticmethod
    def _profile_values() -> dict[str, dict[str, float]]:
        profiles = {
            "conservative": {
                "normal_cooling": 24.5,
                "normal_heating": 20.5,
                "normal_lighting": 0.95,
                "normal_vent": 1.00,
                "normal_equipment": 0.97,
                "eco_cooling": 25.0,
                "eco_heating": 20.0,
                "eco_lighting": 0.85,
                "eco_vent": 0.90,
                "eco_equipment": 0.92,
                "peak_cooling": 25.5,
                "peak_heating": 20.0,
                "peak_lighting": 0.78,
                "peak_vent": 0.85,
                "peak_equipment": 0.88,
            },
            "balanced": {
                "normal_cooling": 25.0,
                "normal_heating": 20.0,
                "normal_lighting": 0.90,
                "normal_vent": 0.95,
                "normal_equipment": 0.95,
                "eco_cooling": 25.5,
                "eco_heating": 19.5,
                "eco_lighting": 0.75,
                "eco_vent": 0.82,
                "eco_equipment": 0.88,
                "peak_cooling": 26.0,
                "peak_heating": 19.0,
                "peak_lighting": 0.65,
                "peak_vent": 0.75,
                "peak_equipment": 0.82,
            },
            "demo": {
                "normal_cooling": 25.2,
                "normal_heating": 19.8,
                "normal_lighting": 0.85,
                "normal_vent": 1.00,
                "normal_equipment": 0.92,
                "eco_cooling": 25.8,
                "eco_heating": 19.2,
                "eco_lighting": 0.65,
                "eco_vent": 0.95,
                "eco_equipment": 0.80,
                "peak_cooling": 26.0,
                "peak_heating": 19.0,
                "peak_lighting": 0.60,
                "peak_vent": 0.90,
                "peak_equipment": 0.75,
            },
        }
        return profiles.get(settings.control_profile, profiles["balanced"])

    @staticmethod
    def _mask_unavailable_controls(state: BuildingState, action: ControlAction) -> ControlAction:
        """Remove targets for actuator groups that the current IDF does not expose."""
        signals = set(state.available_signals or [])
        if "cooling_schedule_actuators" not in signals:
            action.cooling_setpoint_c = None
        if "heating_schedule_actuators" not in signals:
            action.heating_setpoint_c = None
        if "lighting_schedule_actuators" not in signals:
            action.lighting_fraction = None
        if "equipment_schedule_actuators" not in signals:
            action.equipment_fraction = None
        if "ventilation_schedule_actuators" not in signals:
            action.ventilation_fraction = None
        return action

    def _candidate_actions(self, state: BuildingState) -> list[ControlAction]:
        occupied = [zone for zone in state.zones if zone.occupied]
        mean_temp = self._mean(
            [zone.temperature_c for zone in occupied if zone.temperature_c is not None]
        )
        mean_pmv = self._mean([zone.pmv for zone in occupied if zone.pmv is not None])
        max_co2 = max(
            [zone.co2_ppm for zone in occupied if zone.co2_ppm is not None],
            default=None,
        )
        all_max_co2 = max(
            [zone.co2_ppm for zone in state.zones if zone.co2_ppm is not None],
            default=None,
        )
        hour = int(state.calendar.get("hour", 0))
        current_kw = state.facility_kw
        near_peak = state.peak_kw > 0 and current_kw >= 0.90 * state.peak_kw
        cfg = self._profile_values()

        if not occupied:
            if all_max_co2 is not None and all_max_co2 >= 900.0:
                unoccupied_ventilation = 0.60
                iaq_reason = "Residual CO2 is high; temporarily increase ventilation for IAQ recovery."
            elif all_max_co2 is not None and all_max_co2 >= 700.0:
                unoccupied_ventilation = 0.35
                iaq_reason = "Residual CO2 is elevated; maintain moderate ventilation until it clears."
            else:
                unoccupied_ventilation = 0.15
                iaq_reason = "Indoor air quality is stable; use minimum safe ventilation."

            return [
                ControlAction(
                    mode="UNOCCUPIED_SETBACK",
                    cooling_setpoint_c=27.0,
                    heating_setpoint_c=18.0,
                    lighting_fraction=0.05,
                    ventilation_fraction=unoccupied_ventilation,
                    equipment_fraction=0.10,
                    force_when_unoccupied=True,
                    hold_steps=16,
                    reason=(
                        "No occupied zones are detected; apply bounded HVAC setback, "
                        "minimum lighting and non-critical plug-load setback. " + iaq_reason
                    ),
                    confidence=0.99,
                    created_for_step=state.sim_step,
                    source="optimizer",
                )
            ]

        if (
            max_co2 is not None
            and max_co2 >= min(800.0, settings.max_co2_ppm - 150.0)
            and "ventilation_schedule_actuators" in set(state.available_signals or [])
        ):
            recovery_ventilation = 1.35 if max_co2 >= settings.max_co2_ppm else 1.15
            return [
                ControlAction(
                    mode="IAQ_RECOVERY",
                    cooling_setpoint_c=24.5,
                    heating_setpoint_c=20.5,
                    lighting_fraction=0.90,
                    ventilation_fraction=recovery_ventilation,
                    equipment_fraction=0.95,
                    hold_steps=4,
                    reason=(
                        f"Occupied-zone CO2 reached {max_co2:.0f} ppm; prioritize "
                        "outdoor-air recovery before further energy reduction."
                    ),
                    confidence=0.99,
                    created_for_step=state.sim_step,
                    source="optimizer",
                )
            ]

        candidates = [
            ControlAction(
                mode="NORMAL",
                cooling_setpoint_c=cfg["normal_cooling"],
                heating_setpoint_c=cfg["normal_heating"],
                lighting_fraction=cfg["normal_lighting"],
                ventilation_fraction=cfg["normal_vent"],
                equipment_fraction=cfg["normal_equipment"],
                hold_steps=16,
                reason="Maintain conservative comfort while trimming controllable loads.",
                confidence=0.94,
                created_for_step=state.sim_step,
                source="optimizer",
            ),
            ControlAction(
                mode="ECO",
                cooling_setpoint_c=cfg["eco_cooling"],
                heating_setpoint_c=cfg["eco_heating"],
                lighting_fraction=cfg["eco_lighting"],
                ventilation_fraction=cfg["eco_vent"],
                equipment_fraction=cfg["eco_equipment"],
                hold_steps=16,
                reason=(
                    "Use the available comfort margin while reducing lighting, "
                    "ventilation and non-critical plug loads."
                ),
                confidence=0.90,
                created_for_step=state.sim_step,
                source="optimizer",
            ),
            ControlAction(
                mode="PEAK_LIMIT",
                cooling_setpoint_c=cfg["peak_cooling"],
                heating_setpoint_c=cfg["peak_heating"],
                lighting_fraction=cfg["peak_lighting"],
                ventilation_fraction=cfg["peak_vent"],
                equipment_fraction=cfg["peak_equipment"],
                hold_steps=12,
                reason="Reduce discretionary load during a high-demand interval within hard constraints.",
                confidence=0.88,
                created_for_step=state.sim_step,
                source="optimizer",
            ),
        ]

        if (
            11 <= hour <= 14
            and (state.outdoor_temperature_c or 0) >= 31.0
            and (mean_temp is None or mean_temp < 24.6)
        ):
            candidates.append(
                ControlAction(
                    mode="PRECOOL",
                    cooling_setpoint_c=23.5,
                    heating_setpoint_c=20.0,
                    lighting_fraction=0.85,
                    ventilation_fraction=0.90,
                    equipment_fraction=0.90,
                    hold_steps=8,
                    reason="Pre-cool briefly ahead of a hot afternoon peak.",
                    confidence=0.82,
                    created_for_step=state.sim_step,
                    source="optimizer",
                )
            )

        if max_co2 is not None and max_co2 >= settings.max_co2_ppm - 150:
            candidates.append(
                ControlAction(
                    mode="IAQ_RECOVERY",
                    cooling_setpoint_c=24.5,
                    heating_setpoint_c=20.5,
                    lighting_fraction=0.90,
                    ventilation_fraction=1.20,
                    equipment_fraction=0.95,
                    hold_steps=8,
                    reason="Increase outdoor air because occupied-zone CO₂ is approaching its limit.",
                    confidence=0.99,
                    created_for_step=state.sim_step,
                    source="optimizer",
                )
            )

        if (mean_temp is not None and mean_temp >= settings.occupied_temp_max_c - 0.4) or (
            mean_pmv is not None and mean_pmv >= settings.max_abs_pmv - 0.1
        ):
            candidates.append(
                ControlAction(
                    mode="COMFORT_RECOVERY",
                    cooling_setpoint_c=24.0,
                    heating_setpoint_c=20.5,
                    lighting_fraction=0.95,
                    ventilation_fraction=1.0,
                    equipment_fraction=0.95,
                    hold_steps=8,
                    reason="Prioritize comfort because an occupied zone is approaching the warm limit.",
                    confidence=0.99,
                    created_for_step=state.sim_step,
                    source="optimizer",
                )
            )
        if near_peak:
            for candidate in candidates:
                if candidate.mode == "PEAK_LIMIT":
                    candidate.metadata["peak_event"] = True

        return candidates

    def _score(self, state: BuildingState, action: ControlAction) -> OptimizationCandidate:
        predicted_kw = self.surrogate.predict_kw(state, action)
        energy_score = predicted_kw

        occupied = [zone for zone in state.zones if zone.occupied]
        comfort_penalty = 0.0
        iaq_penalty = 0.0
        for zone in occupied:
            if zone.temperature_c is not None:
                projected = zone.temperature_c
                if action.cooling_setpoint_c is not None and zone.temperature_c > action.cooling_setpoint_c:
                    projected -= min(0.5, 0.25 * (zone.temperature_c - action.cooling_setpoint_c))
                if projected > settings.occupied_temp_max_c:
                    comfort_penalty += 1000.0 * (projected - settings.occupied_temp_max_c) ** 2
                elif projected < settings.occupied_temp_min_c:
                    comfort_penalty += 1000.0 * (settings.occupied_temp_min_c - projected) ** 2
                else:
                    comfort_penalty += 1.5 * abs(projected - 24.0)
            if zone.pmv is not None and abs(zone.pmv) > settings.max_abs_pmv:
                comfort_penalty += 1500.0 * (abs(zone.pmv) - settings.max_abs_pmv) ** 2
            if zone.co2_ppm is not None:
                ventilation = action.ventilation_fraction if action.ventilation_fraction is not None else 1.0
                projected_co2 = zone.co2_ppm * (1.0 + max(0.0, 1.0 - ventilation) * 0.08)
                if projected_co2 > settings.max_co2_ppm:
                    iaq_penalty += 3.0 * (projected_co2 - settings.max_co2_ppm)

        switching_penalty = 0.0
        active = state.active_action or {}
        if action.cooling_setpoint_c is not None and active.get("cooling_setpoint_c") is not None:
            switching_penalty += 2.0 * abs(
                action.cooling_setpoint_c - float(active["cooling_setpoint_c"])
            )
        if action.lighting_fraction is not None and active.get("lighting_fraction") is not None:
            switching_penalty += 10.0 * abs(
                action.lighting_fraction - float(active["lighting_fraction"])
            )
        if action.equipment_fraction is not None and active.get("equipment_fraction") is not None:
            switching_penalty += 6.0 * abs(
                action.equipment_fraction - float(active["equipment_fraction"])
            )

        if action.mode == "PRECOOL":
            energy_score += 0.08 * max(state.facility_kw, 1.0)
        elif action.mode == "PEAK_LIMIT" and not action.metadata.get("peak_event"):
            # Avoid selecting the most aggressive candidate when there is no peak.
            energy_score += 0.08 * max(state.facility_kw, 1.0)

        total = energy_score + comfort_penalty + iaq_penalty + switching_penalty
        return OptimizationCandidate(
            action=action,
            predicted_kw=predicted_kw,
            energy_score=energy_score,
            comfort_penalty=comfort_penalty,
            iaq_penalty=iaq_penalty,
            switching_penalty=switching_penalty,
            total_score=total,
        )

    def optimize(self, state: BuildingState) -> OptimizationResult:
        candidates: list[OptimizationCandidate] = []
        for action in self._candidate_actions(state):
            action = self._mask_unavailable_controls(state, action)
            errors, _ = self.constraints.validate(action, state)
            if not errors:
                candidates.append(self._score(state, action))

        if not candidates:
            fallback = safe_fallback_action(
                state, "No optimizer candidate passed the safety constraints"
            )
            candidates = [self._score(state, fallback)]

        candidates.sort(key=lambda candidate: candidate.total_score)
        selected = candidates[0].action
        if state.facility_kw > 0:
            selected.expected_energy_change_pct = (
                (state.facility_kw - candidates[0].predicted_kw) / state.facility_kw * 100.0
            )
        return OptimizationResult(
            selected_action=selected,
            candidates=candidates,
            state_step=state.sim_step,
            explanation=(
                f"Selected {selected.mode} with predicted demand "
                f"{candidates[0].predicted_kw:.2f} kW and objective {candidates[0].total_score:.2f}."
            ),
        )
