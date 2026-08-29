# EcoPilot — Run Me First (Windows)

This build addresses the main causes of low or inconsistent energy savings observed during early testing.

## 1. Install prerequisites

Install:

- Python 3.11 or 3.12
- EnergyPlus (use an IDF from the same EnergyPlus version)
- Ollama only if you want the full LLM mode

## 2. One-time Python setup

Open PowerShell **inside the project root** and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
```

Then open `.env` and set:

```env
ENERGYPLUS_HOME=C:\EnergyPlusV26-2-0
CONTROL_PROFILE=demo
```

Use your real EnergyPlus installation path.

Optional LLM setup:

```powershell
ollama pull qwen3:8b
```

## 3. Prepare the EnergyPlus twins

Recommended simulation setup:

```powershell
.\.venv\Scripts\Activate.ps1
python -m scripts.setup_models --days 5 --start-month 7 --start-day 15
```

The setup script now prefers a Small Office model when available and a hot-weather EPW (Delhi first when installed). It creates:

```text
models/baseline.idf
models/controlled.idf
models/weather.epw
```

Both twins still use the **same** prepared IDF and weather. EcoPilot differs only through runtime actuator overrides.

## 4. Start the dashboard

PowerShell window 1:

```powershell
.\run_dashboard.ps1
```

Or:

```powershell
.\.venv\Scripts\Activate.ps1
python -m streamlit run dashboard/app.py
```

## 5. Run the recommended reliable demo

PowerShell window 2:

```powershell
.\run_demo.ps1 -Profile demo -RealtimeDelay 0.20
```

Equivalent command:

```powershell
.\.venv\Scripts\Activate.ps1
python -m experiments.run_scenarios --deterministic-agent --control-profile demo --realtime-delay 0.20
```

This mode is the recommended way to verify EnergyPlus actuation and the deterministic control pipeline. It uses the deterministic optimizer/fallback path, not the LLM for each action.

## 6. Run the full Ollama + MCP version

Make sure Ollama is running. If needed:

```powershell
ollama serve
```

Then:

```powershell
.\.venv\Scripts\Activate.ps1
python -m experiments.run_scenarios --control-profile demo --realtime-delay 0.25
```

The full mode keeps the LLM as the supervisory layer and falls back to deterministic safe control if the LLM does not complete an actuation cycle.
