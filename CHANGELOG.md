# EcoPilot v0.2.0 — Energy-Savings Reliability Update

- Fixed unoccupied actions being validated but reset to baseline at runtime.
- Added bounded `UNOCCUPIED_SETBACK` control.
- Added ElectricEquipment schedule discovery/control.
- Added outdoor-air schedule creation for blank `DesignSpecification:OutdoorAir` schedules.
- Protected occupancy schedules from accidental control.
- Added duplicate/shared schedule protection.
- Added actuator-aware optimizer masking.
- Added summer weekday model preparation and hot-weather preference.
- Added simulation-step synchronized deterministic control.
- Added hybrid fast deterministic + slower LLM supervisory mode.
- Increased action hold windows to prevent reversion during model latency.
- Changed whole-building cumulative energy to demand integration.
- Fixed live KPI comparison to align baseline and controlled simulation steps.
- No-op actuator writes are now marked `skipped`, not `applied`.
- Added `scripts.diagnose_run` and `scripts.export_results`.
- Added dynamic savings gauge and two-decimal savings display.
- Added one-command Windows helper scripts and `RUN_ME_FIRST.md`.

## v3 — Adaptive IAQ recovery

- Added residual-CO2-aware ventilation during `UNOCCUPIED_SETBACK`.
- Uses 60% ventilation above 900 ppm, 35% from 700–899 ppm, and 15% once IAQ is stable.
- Updated unoccupied safety constraints so high residual CO2 cannot be paired with an overly deep ventilation setback.
- Removed repetitive low-ventilation warnings for safe unoccupied setbacks; occupied low ventilation is still warned.
- Added regression tests for adaptive unoccupied IAQ recovery.

## v4 — IAQ priority + runtime-health classification

- Preserves the v3 residual-CO2-aware unoccupied setback.
- Makes occupied IAQ recovery proactive: when occupied-zone CO2 reaches the recovery threshold and a ventilation actuator is available, IAQ_RECOVERY temporarily takes priority over energy optimization.
- Uses less aggressive occupied ventilation reduction in the demo profile so savings are not achieved by sacrificing indoor air quality.
- Replaces the old `ATTENTION = any ERROR event` dashboard rule with an operational-health classifier.
- The System Health KPI now reports `OPERATIONAL` unless a fatal/critical event or non-zero EnergyPlus exit proves a genuine runtime failure.
- EnergyPlus SEVERE messages, agent/control diagnostics, warnings, and handled safety interventions remain visible separately in the System Health tab; they are not hidden.
