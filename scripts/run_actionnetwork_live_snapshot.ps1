param(
    [string]$Date = "today",
    [string]$Market = "all",
    [switch]$Refresh,
    [int]$Retries = 1
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $Root.Path }
Set-Location $Root

$argsList = @("scripts\actionnetwork_live_snapshot_workflow.py", "--date", $Date, "--market", $Market, "--retries", "$Retries")
if ($Refresh) { $argsList += "--refresh" }
& $Python @argsList
exit $LASTEXITCODE
