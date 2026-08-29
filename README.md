# EcoPilot

**Safety-constrained agentic digital twin for autonomous building energy optimization**

EcoPilot is a building-energy control platform that combines **EnergyPlus**, Python-based optimization, local LLM supervision, MCP tool orchestration, runtime actuator control, safety validation, telemetry, and a real-time dashboard.

The system runs two synchronized EnergyPlus simulations:

- **Baseline twin** — follows the building's native EnergyPlus schedules
- **EcoPilot twin** — applies validated runtime control actions to available HVAC, lighting, equipment, and ventilation actuators

EcoPilot is designed to explore how agentic AI can supervise building operations while keeping deterministic safety logic in the control path.

> For the shortest setup path, start with **[RUN_ME_FIRST.md](RUN_ME_FIRST.md)**.

---

## Core Capabilities

- Synchronized baseline and controlled EnergyPlus twins
- EnergyPlus Runtime API integration
- Runtime sensor feedback and actuator injection
- Local LLM supervision through Ollama
- MCP-based tool discovery and execution
- Deterministic optimization and fallback control
- Cooling and heating setpoint control
- Lighting schedule control
- Non-critical equipment schedule control
- Ventilation schedule control
- Occupancy-aware operating modes
- CO₂-aware IAQ recovery
- Temperature, PMV, deadband, and actuator constraints
- HMAC-bound action approval tokens
- Runtime safety revalidation before actuator writes
- Automatic rollback and safe fallback behavior
- SQLite telemetry, actions, events, and audit history
- Streamlit + Plotly monitoring dashboard
- Real actuator-write auditing
- Diagnostics for actuator discovery and control coverage

---

## System Architecture

```text
                    ┌──────────────────────────┐
                    │      Building Model      │
                    │    EnergyPlus + EPW      │
                    └────────────┬─────────────┘
                                 │
                   ┌─────────────┴─────────────┐
                   │                           │
                   ▼                           ▼
        ┌────────────────────┐      ┌────────────────────┐
        │   Baseline Twin    │      │   EcoPilot Twin    │
        │ Native schedules   │      │ Runtime overrides  │
        └─────────┬──────────┘      └─────────┬──────────┘
                  │                           │
                  │                           ▼
                  │                 ┌────────────────────┐
                  │                 │ Sensor / State Bus │
                  │                 └─────────┬──────────┘
                  │                           │
                  │                           ▼
                  │                 ┌────────────────────┐
                  │                 │ Optimizer + Agent  │
                  │                 │  Ollama + MCP      │
                  │                 └─────────┬──────────┘
                  │                           │
                  │                           ▼
                  │                 ┌────────────────────┐
                  │                 │   Safety Shield    │
                  │                 │ Validation + Token │
                  │                 └─────────┬──────────┘
                  │                           │
                  │                           ▼
                  │                 ┌────────────────────┐
                  │                 │ Actuator Injection │
                  │                 └─────────┬──────────┘
                  │                           │
                  └─────────────┬─────────────┘
                                ▼
                    ┌──────────────────────────┐
                    │ SQLite + Dashboard       │
                    │ Telemetry / Audit / UI   │
                    └──────────────────────────┘
```

---

## Closed-Loop Workflow

At each relevant simulation step, EcoPilot performs the following workflow:

1. Read EnergyPlus telemetry.
2. Build the current building state.
3. Evaluate occupancy, temperature, CO₂, PMV, demand, and available actuators.
4. Select an operating strategy.
5. Generate candidate control actions.
6. Validate the candidate against hard safety constraints.
7. Bind approved actions to the simulation step using an HMAC approval token.
8. Revalidate the action inside the controlled EnergyPlus process.
9. Write approved values to available actuators.
10. Store telemetry, decisions, validation status, and actuator-write information in SQLite.
11. Update the Streamlit dashboard.

The LLM acts as a **supervisory reasoning layer**. Safety-critical actuator enforcement remains deterministic.

---

## Operating Modes

EcoPilot can use operating modes such as:

| Mode | Purpose |
|---|---|
| `NORMAL` | Standard building operation |
| `ECO` | Energy-aware occupied operation |
| `UNOCCUPIED_SETBACK` | Reduced conditioning and non-critical loads when zones are unoccupied |
| `IAQ_RECOVERY` | Increased ventilation when indoor CO₂ requires attention |
| `PRECOOL` | Pre-conditioning before an expected occupied/high-load period |
| `PEAK_LIMIT` | Demand-aware control strategy |
| `COMFORT_RECOVERY` | Restores tighter comfort control when conditions drift |
| `SAFE_FALLBACK` | Conservative fallback when a proposed action cannot be safely applied |

Available modes depend on the current state and discovered EnergyPlus actuators.

---

## Control Profiles

EcoPilot supports three control profiles:

| Profile | Description |
|---|---|
| `conservative` | Minimal intervention |
| `balanced` | General-purpose operation |
| `demo` | Stronger short-run control while preserving hard safety constraints |

The selected profile affects candidate aggressiveness, not the underlying safety checks.

---

## Repository Structure

```text
ecopilot/
├── agent/                 # LLM/MCP supervisory orchestration
├── control/               # optimizer, surrogate, constraints, safety and fallback
├── core/                  # configuration and SQLite state/action/event bus
├── dashboard/             # Streamlit control center
├── energyplus/            # callbacks, sensors, actuators and IDF preparation
├── experiments/           # dual-twin launcher and experiment utilities
├── mcp_server/            # MCP server and control tools
├── models/                # baseline.idf, controlled.idf and weather.epw
├── scripts/               # setup and diagnostics utilities
├── tests/                 # unit tests and optional EnergyPlus integration test
├── docs/                  # architecture and supporting documentation
├── data/                  # local runtime data (ignored by Git)
├── .streamlit/
├── .env.example
├── .gitignore
├── README.md
├── RUN_ME_FIRST.md
├── requirements.txt
├── pyproject.toml
├── setup_windows.ps1
├── run_dashboard.ps1
└── run_demo.ps1
```

---

# Quick Start — Windows

## 1. Prerequisites

Install:

- Python 3.10+
- EnergyPlus
- Git
- Ollama — only required for the LLM-supervised mode

---

## 2. Create the Python environment

Open PowerShell in the project folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
```

If you prefer to create the environment manually:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

---

## 3. Configure the project

Copy the example configuration:

```powershell
Copy-Item .env.example .env
```

Open `.env` and set your EnergyPlus installation path:

```env
ENERGYPLUS_HOME=C:\EnergyPlusV26-1-0
CONTROL_PROFILE=demo
```

Use the actual EnergyPlus directory installed on your computer.

The local `.env` file is intentionally ignored by Git.

---

## 4. Prepare the EnergyPlus models

For a five-day summer simulation:

```powershell
.\.venv\Scripts\Activate.ps1

python -m scripts.setup_models `
    --days 5 `
    --start-month 7 `
    --start-day 15
```

To use your own building and weather files:

```powershell
python -m scripts.setup_models `
    --idf "C:\path\building.idf" `
    --weather "C:\path\weather.epw" `
    --days 5 `
    --start-month 7 `
    --start-day 15
```

Prepared files are stored in `models/`.

---

## 5. Start the Dashboard

Open a PowerShell window in the project directory:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py
```

You can also use:

```powershell
.\run_dashboard.ps1
```

Leave this terminal running.

---

## 6. Run the Deterministic Controller

Open a second PowerShell window:

```powershell
.\.venv\Scripts\Activate.ps1

python -m experiments.run_scenarios `
    --deterministic-agent `
    --control-profile demo `
    --realtime-delay 0.20
```

Or use:

```powershell
.\run_demo.ps1 -Profile demo -RealtimeDelay 0.20
```

This mode does not require Ollama.

---

# LLM + MCP Mode

## 1. Install the local model

```powershell
ollama pull qwen3:8b
```

## 2. Start Ollama

```powershell
ollama serve
```

Keep that terminal open.

## 3. Start EcoPilot

In another PowerShell window:

```powershell
.\.venv\Scripts\Activate.ps1

python -m experiments.run_scenarios `
    --control-profile demo `
    --realtime-delay 0.25
```

The deterministic control path remains available while the LLM provides supervisory reasoning.

---

## Actuator Discovery

EcoPilot discovers available EnergyPlus control points at runtime.

During a controlled simulation, actuator information is written locally to:

```text
data/live/exchange_points_controlled.json
```

A typical structure is:

```json
{
  "selected_actuators": {
    "cooling": [],
    "heating": [],
    "lighting": [],
    "equipment": [],
    "ventilation": []
  }
}
```

If a schedule is not discovered automatically, its exact name can be configured in `.env`:

```env
CONTROLLED_COOLING_SCHEDULES=CLGSETP_SCH
CONTROLLED_HEATING_SCHEDULES=HTGSETP_SCH
CONTROLLED_LIGHTING_SCHEDULES=LIGHTS_SCH
CONTROLLED_EQUIPMENT_SCHEDULES=EQUIP_SCH
CONTROLLED_VENTILATION_SCHEDULES=MINOA_SCH
```

Restart the simulation after changing actuator mappings.

---

## Diagnostics

After a run, inspect the control integration with:

```powershell
python -m scripts.diagnose_run
```

The diagnostic utility can be used to inspect:

- discovered actuator groups
- real actuator writes
- control coverage
- occupancy visibility
- baseline/controlled synchronization
- periods where control changed facility demand
- potential integration issues

Generated diagnostic and runtime files remain local and can be excluded from the public repository through `.gitignore`.

---

## Dashboard

EcoPilot provides four main dashboard views:

### Command Overview

High-level twin status, demand trends, building state, active strategy, and operational KPIs.

### Zone Intelligence

Zone-level information such as:

- temperature
- occupancy
- CO₂
- PMV
- heating setpoint
- cooling setpoint

### Agent Decisions

Displays:

- current control mode
- proposed targets
- validation state
- action history
- actuator-write status
- reasoning/audit information

### System Health

Displays:

- baseline twin status
- controlled twin status
- simulation progress
- runtime warnings
- EnergyPlus diagnostics
- agent/control diagnostics
- safety interventions
- critical runtime conditions

---

## Safety Model

EcoPilot does not allow the supervisory agent to write arbitrary actuator values directly.

Every action passes through deterministic validation.

The control pipeline checks:

- heating and cooling bounds
- minimum thermostat deadband
- maximum setpoint changes
- occupied temperature constraints
- PMV constraints
- CO₂ / IAQ conditions
- actuator availability
- occupancy-dependent rules
- action freshness
- approval-token validity

Approved actions receive an HMAC token tied to the exact payload and simulation step.

Before writing an EnergyPlus actuator, the controlled simulation validates the action again. Invalid, stale, modified, unsafe, or unavailable actions are rejected or skipped.

---

## Data and Privacy

Runtime information is stored locally in SQLite and generated files under `data/`.

The public repository should not include:

```text
.env
.venv/
data/ecopilot.db
data/live/
data/baseline/
data/controlled/
results/
__pycache__/
.pytest_cache/
*.pyc
```

Use `.env.example` for configuration examples.

---

## Testing

Run the test suite with:

```powershell
pytest
```

The test suite covers areas including:

- optimizer behavior
- occupancy-aware setback
- IAQ-aware control
- setpoint and deadband constraints
- HMAC action approval
- IDF parsing
- equipment actuator discovery
- outdoor-air schedule handling
- synchronized twin comparison
- SQLite state/action storage

The EnergyPlus integration test requires a local EnergyPlus installation and may be skipped when EnergyPlus is unavailable.

---

## Technology Stack

- **Python**
- **EnergyPlus**
- **EnergyPlus Python Runtime API**
- **Model Context Protocol (MCP)**
- **Ollama**
- **Qwen3**
- **Streamlit**
- **Plotly**
- **SQLite**
- **Pydantic**

---

## Project Scope

EcoPilot is an experimental software platform for studying AI-supervised building control in simulation.

Its behavior depends on factors such as:

- building model
- weather file
- occupancy schedules
- native HVAC schedules
- available EnergyPlus actuators
- selected control profile
- comfort constraints
- indoor-air-quality constraints

It should therefore be evaluated using controlled and reproducible EnergyPlus simulations rather than assuming a fixed outcome across different buildings or operating conditions.

---

## References

- EnergyPlus Python API: https://energyplus.readthedocs.io/en/latest/api.html
- EnergyPlus Runtime API: https://energyplus.readthedocs.io/en/latest/runtime.html
- EnergyPlus Data Transfer API: https://energyplus.readthedocs.io/en/latest/datatransfer.html
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Ollama Tool Calling: https://docs.ollama.com/capabilities/tool-calling
