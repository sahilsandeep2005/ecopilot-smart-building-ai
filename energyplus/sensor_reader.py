from __future__ import annotations

from typing import Any

from agent.schemas import BuildingState, ZoneState
from core.utils import utc_now_iso
from energyplus.handle_registry import HandleRegistry


class SensorReader:
    def __init__(self, api: Any, registry: HandleRegistry, run_id: str, mode: str):
        self.api = api
        self.exchange = api.exchange
        self.registry = registry
        self.run_id = run_id
        self.mode = mode
        self.cumulative_kwh = 0.0
        self.hvac_cumulative_joules = 0.0
        self.peak_kw = 0.0

    def _variable(self, state: Any, handle: int) -> float | None:
        if handle < 0:
            return None
        value = float(self.exchange.get_variable_value(state, handle))
        if self.exchange.api_error_flag(state):
            self.exchange.reset_api_error_flag(state)
            return None
        return value

    def _meter(self, state: Any, handle: int) -> float | None:
        if handle < 0:
            return None
        value = float(self.exchange.get_meter_value(state, handle))
        if self.exchange.api_error_flag(state):
            self.exchange.reset_api_error_flag(state)
            return None
        return value

    def _zone_pmv(self, state: Any, zone_name: str) -> float | None:
        values: list[float] = []
        for people_name, people_zone in self.registry.model_info.people_to_zone.items():
            if people_zone.upper() != zone_name.upper():
                continue
            value = self._variable(state, self.registry.people_pmv_handles.get(people_name, -1))
            if value is not None:
                values.append(value)
        return sum(values) / len(values) if values else None

    def _zone_timestep_hours(self, state: Any) -> float:
        dt_hours = 0.0
        zone_timestep = getattr(self.exchange, "zone_time_step", None)
        if zone_timestep is not None:
            try:
                dt_hours = float(zone_timestep(state))
            except Exception:
                dt_hours = 0.0
        if dt_hours <= 0:
            steps_per_hour = max(1, int(self.exchange.num_time_steps_in_hour(state)))
            dt_hours = 1.0 / steps_per_hour
        return dt_hours

    def read(
        self,
        state: Any,
        sim_step: int,
        active_action: dict | None,
        runtime_summary: dict,
    ) -> BuildingState:
        zones: list[ZoneState] = []
        total_occupants = 0.0
        for zone_name, handles in self.registry.zone_handles.items():
            occupants = self._variable(state, handles.get("occupants", -1)) or 0.0
            total_occupants += occupants
            zones.append(
                ZoneState(
                    name=zone_name,
                    temperature_c=self._variable(state, handles.get("temperature_c", -1)),
                    relative_humidity_pct=self._variable(
                        state, handles.get("relative_humidity_pct", -1)
                    ),
                    pmv=self._zone_pmv(state, zone_name),
                    co2_ppm=self._variable(state, handles.get("co2_ppm", -1)),
                    occupants=occupants,
                    occupied=occupants > 0.1,
                    cooling_setpoint_c=self._variable(
                        state, handles.get("cooling_setpoint_c", -1)
                    ),
                    heating_setpoint_c=self._variable(
                        state, handles.get("heating_setpoint_c", -1)
                    ),
                )
            )

        dt_hours = self._zone_timestep_hours(state)
        demand_watts = self._variable(state, self.registry.facility_demand_handle)
        facility_meter_joules = self._meter(state, self.registry.facility_meter_handle)

        # EnergyPlus documents get_meter_value() as a *current* meter value rather
        # than a cumulative total. For whole-building energy, integrating the
        # reported facility demand over the zone timestep gives a stable cumulative
        # value and avoids version/model differences in meter exposure.
        if demand_watts is not None:
            facility_kw = max(0.0, demand_watts / 1000.0)
            step_kwh = facility_kw * dt_hours
        else:
            meter_j = max(0.0, facility_meter_joules or 0.0)
            step_kwh = meter_j / 3_600_000.0
            facility_kw = step_kwh / dt_hours if dt_hours > 0 else 0.0

        self.cumulative_kwh += step_kwh
        self.peak_kw = max(self.peak_kw, facility_kw)

        hvac_joules = self._meter(state, self.registry.hvac_meter_handle)
        if hvac_joules is not None:
            self.hvac_cumulative_joules += max(0.0, hvac_joules)

        return BuildingState(
            run_id=self.run_id,
            mode=self.mode,
            sim_step=sim_step,
            sim_time_hours=float(self.exchange.current_sim_time(state)),
            timestamp_utc=utc_now_iso(),
            calendar={
                "month": int(self.exchange.month(state)),
                "day": int(self.exchange.day_of_month(state)),
                "hour": int(self.exchange.hour(state)),
                "minute": int(self.exchange.minutes(state)),
                "day_of_week": int(self.exchange.day_of_week(state)),
            },
            outdoor_temperature_c=self._variable(
                state, self.registry.environment_handles.get("outdoor_temperature_c", -1)
            ),
            outdoor_relative_humidity_pct=self._variable(
                state,
                self.registry.environment_handles.get("outdoor_relative_humidity_pct", -1),
            ),
            facility_kw=facility_kw,
            cumulative_kwh=self.cumulative_kwh,
            peak_kw=self.peak_kw,
            hvac_kwh=self.hvac_cumulative_joules / 3_600_000.0,
            total_occupants=total_occupants,
            zones=zones,
            active_action=active_action,
            available_signals=self.registry.availability_summary(),
            runtime=runtime_summary,
        )
