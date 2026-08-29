from types import SimpleNamespace

from agent.schemas import ControlAction
from energyplus.actuator_writer import ActuatorWriter
from energyplus.handle_registry import ScheduleHandle


class FakeExchange:
    def __init__(self):
        self.values = {}
        self.resets = []

    def set_actuator_value(self, state, handle, value):
        self.values[handle] = value

    def reset_actuator(self, state, handle):
        self.resets.append(handle)
        self.values.pop(handle, None)


class FakeApi:
    def __init__(self):
        self.exchange = FakeExchange()


def test_writer_applies_all_available_control_groups():
    api = FakeApi()
    registry = SimpleNamespace(
        cooling_schedules=[ScheduleHandle("cool", "Schedule:Constant", 1, 11)],
        heating_schedules=[ScheduleHandle("heat", "Schedule:Constant", 2, 12)],
        lighting_schedules=[ScheduleHandle("lights", "Schedule:Constant", 3, 13)],
        equipment_schedules=[ScheduleHandle("equip", "Schedule:Constant", 4, 14)],
        ventilation_schedules=[ScheduleHandle("oa", "Schedule:Constant", 5, 15)],
    )
    writer = ActuatorWriter(api, registry)
    action = ControlAction(
        mode="ECO",
        cooling_setpoint_c=25.5,
        heating_setpoint_c=19.5,
        lighting_fraction=0.75,
        equipment_fraction=0.85,
        ventilation_fraction=0.8,
        reason="Test real multi-load actuation",
        confidence=0.9,
    )
    details = writer.apply(None, action, total_occupants=10)
    assert details["reset_to_baseline"] is False
    assert details["actuator_counts"]["equipment"] == 1
    assert details["applied_values"] == {
        "cool": 25.5,
        "heat": 19.5,
        "lights": 0.75,
        "equip": 0.85,
        "oa": 0.8,
    }


def test_writer_allows_authorized_unoccupied_setback():
    api = FakeApi()
    registry = SimpleNamespace(
        cooling_schedules=[], heating_schedules=[], lighting_schedules=[],
        equipment_schedules=[ScheduleHandle("equip", "Schedule:Constant", 4, 14)],
        ventilation_schedules=[],
    )
    writer = ActuatorWriter(api, registry)
    action = ControlAction(
        mode="UNOCCUPIED_SETBACK",
        equipment_fraction=0.10,
        force_when_unoccupied=True,
        reason="Test unoccupied equipment setback",
        confidence=0.99,
    )
    details = writer.apply(None, action, total_occupants=0)
    assert details["reset_to_baseline"] is False
    assert details["applied_values"]["equip"] == 0.10
