from core.health import summarize_system_health


def test_recoverable_diagnostics_do_not_mark_runtime_failed():
    events = [
        {"severity": "WARNING", "source": "controlled_runner", "message": "Runtime safety recheck rejected an action."},
        {"severity": "ERROR", "source": "energyplus:controlled", "message": "** Severe ** Example diagnostic"},
        {"severity": "INFO", "source": "energyplus:controlled", "message": "Simulation finished with exit code 0."},
    ]
    health = summarize_system_health(events)
    assert health["status"] == "OPERATIONAL"
    assert health["runtime_failures"] == 0
    assert health["recoverable_diagnostics"] == 1
    assert health["safety_interventions"] == 1


def test_nonzero_energyplus_exit_marks_critical():
    events = [
        {"severity": "ERROR", "source": "energyplus:controlled", "message": "Simulation finished with exit code 1."},
    ]
    health = summarize_system_health(events)
    assert health["status"] == "CRITICAL"
    assert health["runtime_failures"] == 1
