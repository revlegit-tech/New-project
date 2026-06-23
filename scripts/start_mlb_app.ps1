param(
    [int]$Port = 8765,
    [string]$Host = "127.0.0.1",
    [switch]$SkipBootstrap,
    [switch]$NoBrowser,
    [string]$Date = "today"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Expected virtualenv Python at $Python"
}

if (-not $env:PYTHONPATH) { $env:PYTHONPATH = $Root.Path }
if (-not $env:DB_ENABLED) { $env:DB_ENABLED = "1" }
if (-not $env:DB_FALLBACK_TO_CSV) { $env:DB_FALLBACK_TO_CSV = "1" }
if (-not $env:DATABASE_URL) { $env:DATABASE_URL = "sqlite:///C:/tmp/revlegit_warehouse.sqlite3" }
if (-not $env:GAME_MARKET_ENRICHMENT_ENABLED) { $env:GAME_MARKET_ENRICHMENT_ENABLED = "1" }
if (-not $env:TEAM_GAME_MARKET_PROJECTIONS_ENABLED) { $env:TEAM_GAME_MARKET_PROJECTIONS_ENABLED = "0" }

Set-Location $Root

if (-not $SkipBootstrap) {
    & $Python "scripts\bootstrap_mlb_app.py" --date $Date
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Launch bootstrap returned exit code $LASTEXITCODE; starting FastAPI anyway."
    }
}

$Url = "http://$Host`:$Port"
if (-not $NoBrowser) {
    Start-Process $Url
}

& $Python -m uvicorn mlb_app.asgi:app --host $Host --port $Port
