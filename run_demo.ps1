param(
    [ValidateSet("conservative", "balanced", "demo")]
    [string]$Profile = "demo",
    [double]$RealtimeDelay = 0.20
)

$ErrorActionPreference = "Stop"
& .\.venv\Scripts\Activate.ps1
python -m experiments.run_scenarios --deterministic-agent --control-profile $Profile --realtime-delay $RealtimeDelay
