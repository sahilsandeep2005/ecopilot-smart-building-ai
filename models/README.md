# Building model files

Generate the EnergyPlus files from the same EnergyPlus version installed on the machine:

```powershell
python -m scripts.setup_models --days 5 --start-month 7 --start-day 15
```

This creates:

```text
baseline.idf
controlled.idf
weather.epw
```

The two IDFs are intentionally identical after preparation. The baseline follows native schedules; the controlled twin is differentiated only by runtime actuator overrides.

The preparation step also:

- shortens the weather RunPeriod to a reproducible summer weekday window;
- enables CO₂ reporting;
- adds a 1.0 outdoor-air multiplier when `DesignSpecification:OutdoorAir` has no schedule, so the controlled twin can perform demand-controlled ventilation without changing baseline behavior;
- preserves occupancy schedules from accidental load-control overrides.

Use `data/live/exchange_points_controlled.json` after startup to verify the actual actuator handles exposed by the selected IDF.
