param(
    [string]$Date = "today"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $Root.Path }
Set-Location $Root

& $Python "daily_ml_workflow.py" --date $Date run-daily
exit $LASTEXITCODE
