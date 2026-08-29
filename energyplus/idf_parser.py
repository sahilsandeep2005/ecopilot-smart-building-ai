from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from core.config import settings


def _remove_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        in_quote = False
        result: list[str] = []
        for char in line:
            if char == '"':
                in_quote = not in_quote
            if char == "!" and not in_quote:
                break
            result.append(char)
        lines.append("".join(result))
    return "\n".join(lines)


def _split_objects(text: str) -> list[str]:
    objects: list[str] = []
    buffer: list[str] = []
    in_quote = False
    for char in text:
        if char == '"':
            in_quote = not in_quote
        if char == ";" and not in_quote:
            value = "".join(buffer).strip()
            if value:
                objects.append(value)
            buffer = []
        else:
            buffer.append(char)
    return objects


def _split_fields(raw_object: str) -> list[str]:
    reader = csv.reader([raw_object.replace("\r", " ").replace("\n", " ")], skipinitialspace=True)
    values = next(reader, [])
    return [value.strip().strip('"') for value in values]


def parse_idf(path: Path | str) -> list[list[str]]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    clean = _remove_comments(text)
    return [fields for raw in _split_objects(clean) if (fields := _split_fields(raw))]


def write_idf(objects: Iterable[list[str]], path: Path | str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for fields in objects:
        if not fields:
            continue
        lines.append(f"{fields[0]},")
        for index, field_value in enumerate(fields[1:], start=1):
            suffix = ";" if index == len(fields) - 1 else ","
            lines.append(f"  {field_value}{suffix}")
        lines.append("")
    destination.write_text("\n".join(lines), encoding="utf-8")


@dataclass
class IDFModelInfo:
    path: str
    zones: list[str] = field(default_factory=list)
    people_to_zone: dict[str, str] = field(default_factory=dict)
    cooling_schedules: dict[str, str] = field(default_factory=dict)
    heating_schedules: dict[str, str] = field(default_factory=dict)
    lighting_schedules: dict[str, str] = field(default_factory=dict)
    equipment_schedules: dict[str, str] = field(default_factory=dict)
    ventilation_schedules: dict[str, str] = field(default_factory=dict)
    protected_schedules: list[str] = field(default_factory=list)
    all_schedule_types: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def inspect_idf(path: Path | str) -> IDFModelInfo:
    objects = parse_idf(path)
    info = IDFModelInfo(path=str(Path(path).resolve()))

    schedule_types: dict[str, str] = {}
    for fields in objects:
        object_type = fields[0].upper()
        if object_type.startswith("SCHEDULE:") and len(fields) > 1:
            schedule_types[fields[1]] = fields[0]
    info.all_schedule_types = schedule_types

    # Schedules used to determine occupancy must never be overridden indirectly by
    # lighting/equipment control, otherwise the controlled twin would change its own
    # occupancy signal and the comparison would no longer be fair.
    protected: set[str] = set()
    for fields in objects:
        if fields[0].upper() == "PEOPLE":
            if len(fields) > 3 and fields[3]:
                protected.add(fields[3])  # Number of People Schedule Name
            # Activity-level schedule is also kept protected when present.
            if len(fields) > 10 and fields[10] in schedule_types:
                protected.add(fields[10])
    info.protected_schedules = sorted(protected)

    for fields in objects:
        object_type = fields[0].upper()
        if object_type == "ZONE" and len(fields) > 1:
            info.zones.append(fields[1])
        elif object_type == "PEOPLE" and len(fields) > 2:
            info.people_to_zone[fields[1]] = fields[2]
        elif object_type == "THERMOSTATSETPOINT:DUALSETPOINT" and len(fields) > 3:
            heating_schedule, cooling_schedule = fields[2], fields[3]
            if heating_schedule:
                info.heating_schedules[heating_schedule] = schedule_types.get(heating_schedule, "Schedule:Compact")
            if cooling_schedule:
                info.cooling_schedules[cooling_schedule] = schedule_types.get(cooling_schedule, "Schedule:Compact")
        elif object_type == "THERMOSTATSETPOINT:SINGLEHEATING" and len(fields) > 2:
            schedule = fields[2]
            if schedule:
                info.heating_schedules[schedule] = schedule_types.get(schedule, "Schedule:Compact")
        elif object_type == "THERMOSTATSETPOINT:SINGLECOOLING" and len(fields) > 2:
            schedule = fields[2]
            if schedule:
                info.cooling_schedules[schedule] = schedule_types.get(schedule, "Schedule:Compact")
        elif object_type == "LIGHTS" and len(fields) > 3:
            schedule = fields[3]
            if schedule and schedule not in protected:
                info.lighting_schedules[schedule] = schedule_types.get(schedule, "Schedule:Compact")
        elif object_type == "ELECTRICEQUIPMENT" and len(fields) > 3:
            schedule = fields[3]
            if schedule and schedule not in protected:
                info.equipment_schedules[schedule] = schedule_types.get(schedule, "Schedule:Compact")

    # Discover outdoor-air schedules from common ventilation-related objects.
    # We only accept fields that exactly match a declared Schedule:* name.
    ventilation_objects = {
        "DESIGNSPECIFICATION:OUTDOORAIR",
        "CONTROLLER:OUTDOORAIR",
        "CONTROLLER:MECHANICALVENTILATION",
        "ZONEHVAC:OUTDOORAIRUNIT",
    }
    ventilation_keywords = ("VENT", "MIN OA", "MINOA", "OUTDOOR AIR", "FRESH AIR", "OA SCHED")
    for fields in objects:
        object_type = fields[0].upper()
        if object_type in ventilation_objects:
            for value in fields[2:]:
                if value in schedule_types and value not in protected:
                    info.ventilation_schedules[value] = schedule_types[value]

    for schedule_name, schedule_type in schedule_types.items():
        upper_name = schedule_name.upper()
        if schedule_name not in protected and any(keyword in upper_name for keyword in ventilation_keywords):
            info.ventilation_schedules[schedule_name] = schedule_type

    def merge_overrides(target: dict[str, str], overrides: tuple[str, ...]) -> None:
        for name in overrides:
            target[name] = schedule_types.get(name, "Schedule:Compact")

    merge_overrides(info.cooling_schedules, settings.controlled_cooling_schedules)
    merge_overrides(info.heating_schedules, settings.controlled_heating_schedules)
    merge_overrides(info.lighting_schedules, settings.controlled_lighting_schedules)
    merge_overrides(info.equipment_schedules, settings.controlled_equipment_schedules)
    merge_overrides(info.ventilation_schedules, settings.controlled_ventilation_schedules)

    # Avoid assigning the same shared schedule to multiple control groups.  A single
    # Schedule Value actuator is global: the last write would otherwise silently win.
    claimed: set[str] = set()
    for group in (
        info.cooling_schedules,
        info.heating_schedules,
        info.lighting_schedules,
        info.equipment_schedules,
        info.ventilation_schedules,
    ):
        for name in list(group):
            if name in claimed:
                group.pop(name, None)
            else:
                claimed.add(name)

    info.zones = list(dict.fromkeys(info.zones))
    return info


def ensure_oa_control_schedule(objects: list[list[str]]) -> None:
    """Ensure DesignSpecification:OutdoorAir objects expose a schedulable multiplier.

    Many example IDFs leave Outdoor Air Schedule Name blank, which means there is
    no Schedule Value actuator for demand-controlled ventilation. We add a 1.0
    multiplier only where that field is blank. Because both baseline and controlled
    twins are generated from the same prepared IDF, the baseline behavior remains
    unchanged while the controlled twin gains a legitimate runtime actuator.
    """
    schedule_name = "EcoPilot OA Multiplier"
    needs_schedule = False
    for fields in objects:
        if fields and fields[0].upper() == "DESIGNSPECIFICATION:OUTDOORAIR":
            while len(fields) < 8:
                fields.append("")
            if not fields[7]:
                fields[7] = schedule_name
                needs_schedule = True

    if not needs_schedule:
        return

    exists = any(
        len(fields) > 1
        and fields[0].upper().startswith("SCHEDULE:")
        and fields[1].upper() == schedule_name.upper()
        for fields in objects
    )
    if not exists:
        objects.append(["Schedule:Constant", schedule_name, "", "1.0"])


def enable_co2_simulation(objects: list[list[str]]) -> None:
    """Enable EnergyPlus zone CO2 calculations and timestep output."""
    outdoor_schedule_name = "EcoPilot Outdoor CO2"

    schedule_exists = any(
        len(fields) > 1
        and fields[0].upper().startswith("SCHEDULE:")
        and fields[1].upper() == outdoor_schedule_name.upper()
        for fields in objects
    )
    if not schedule_exists:
        objects.append(["Schedule:Constant", outdoor_schedule_name, "", "400"])

    contaminant_balance = next(
        (fields for fields in objects if fields and fields[0].upper() == "ZONEAIRCONTAMINANTBALANCE"),
        None,
    )
    if contaminant_balance is None:
        objects.append(
            [
                "ZoneAirContaminantBalance",
                "Yes",
                outdoor_schedule_name,
                "No",
                "",
            ]
        )
    else:
        while len(contaminant_balance) < 5:
            contaminant_balance.append("")
        contaminant_balance[1] = "Yes"
        contaminant_balance[2] = outdoor_schedule_name

    output_exists = any(
        len(fields) > 2
        and fields[0].upper() == "OUTPUT:VARIABLE"
        and fields[2].upper() == "ZONE AIR CO2 CONCENTRATION"
        for fields in objects
    )
    if not output_exists:
        objects.append(["Output:Variable", "*", "Zone Air CO2 Concentration", "Timestep"])


def prepare_demo_idf(
    source: Path | str,
    destination: Path | str,
    days: int = 3,
    start_month: int = 7,
    start_day: int = 15,
) -> None:
    """Create a short, reproducible weather run for the EcoPilot PoC.

    The original starter used January, which often produced a heating-dominated
    scenario while the control candidates were primarily cooling-oriented.  The
    default is now a summer weekday window so thermostat, lighting and ventilation
    controls have a measurable opportunity to affect demand.
    """
    objects = parse_idf(source)
    has_run_period = False
    demo_days = max(1, min(int(days), 14))
    # Keep the short demo inside one month for simple, deterministic setup.
    start_month = max(1, min(int(start_month), 12))
    start_day = max(1, min(int(start_day), 28 - demo_days + 1))
    end_day = start_day + demo_days - 1

    for fields in objects:
        object_type = fields[0].upper()
        if object_type == "RUNPERIOD":
            has_run_period = True
            while len(fields) < 14:
                fields.append("")
            fields[2] = str(start_month)
            fields[3] = str(start_day)
            fields[4] = ""
            fields[5] = str(start_month)
            fields[6] = str(end_day)
            fields[7] = ""
            fields[8] = "Monday"
        elif object_type == "TIMESTEP":
            if len(fields) == 1:
                fields.append("4")
            else:
                fields[1] = "4"
        elif object_type == "SIMULATIONCONTROL":
            while len(fields) < 6:
                fields.append("")
            fields[4] = "No"
            fields[5] = "Yes"

    if not has_run_period:
        objects.append([
            "RunPeriod",
            "EcoPilot Demo",
            str(start_month),
            str(start_day),
            "",
            str(start_month),
            str(end_day),
            "",
            "Monday",
            "Yes",
            "Yes",
            "No",
            "Yes",
            "Yes",
        ])
    ensure_oa_control_schedule(objects)
    enable_co2_simulation(objects)
    write_idf(objects, destination)

