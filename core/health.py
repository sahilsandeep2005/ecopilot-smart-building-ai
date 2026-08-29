from __future__ import annotations

from typing import Any


def summarize_system_health(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify runtime health without treating every handled diagnostic as a failure.

    EnergyPlus can emit SEVERE diagnostics and the agent can log recoverable errors while
    the overall closed loop continues and both simulations still exit successfully.  The
    dashboard therefore distinguishes *runtime failures* from model/agent diagnostics.
    Nothing is hidden: detailed counts remain visible in the System Health tab.
    """

    warning_events = 0
    critical_events = 0
    runtime_failures = 0
    energyplus_severe_events = 0
    agent_error_events = 0
    control_error_events = 0
    safety_interventions = 0

    for event in events:
        severity = str(event.get("severity", "")).upper()
        source = str(event.get("source", ""))
        message = str(event.get("message", ""))
        lower_message = message.lower()

        if severity == "WARNING":
            warning_events += 1
            if source == "controlled_runner" and (
                "rejected" in lower_message or "skipped" in lower_message
            ):
                safety_interventions += 1

        if severity == "CRITICAL":
            critical_events += 1

        if severity == "ERROR":
            if source.startswith("energyplus:"):
                # A non-zero EnergyPlus process exit is a genuine integration failure.
                if "simulation finished with exit code" in lower_message and "exit code 0" not in lower_message:
                    runtime_failures += 1
                elif "** severe **" in lower_message:
                    energyplus_severe_events += 1
                else:
                    # Preserve other EnergyPlus errors as model diagnostics unless a
                    # non-zero exit/fatal event proves the run itself failed.
                    energyplus_severe_events += 1
            elif source == "agent":
                agent_error_events += 1
            elif source == "controlled_runner":
                control_error_events += 1
            else:
                # Unknown ERROR sources are conservatively counted as recoverable
                # diagnostics; CRITICAL/non-zero exits still drive failure state.
                control_error_events += 1

    recoverable_diagnostics = (
        energyplus_severe_events + agent_error_events + control_error_events
    )

    if critical_events > 0 or runtime_failures > 0:
        status = "CRITICAL"
        tone = "bad"
        color = "red"
    else:
        # OPERATIONAL means the closed loop is running/finished successfully even
        # if model diagnostics or handled safety events were recorded.
        status = "OPERATIONAL"
        tone = "good"
        color = "green"

    return {
        "status": status,
        "tone": tone,
        "color": color,
        "warning_events": warning_events,
        "critical_events": critical_events,
        "runtime_failures": runtime_failures,
        "energyplus_severe_events": energyplus_severe_events,
        "agent_error_events": agent_error_events,
        "control_error_events": control_error_events,
        "recoverable_diagnostics": recoverable_diagnostics,
        "safety_interventions": safety_interventions,
    }
