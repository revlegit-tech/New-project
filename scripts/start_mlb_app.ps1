param(
    [int]$Port = 8765,
    [string]$BindHost = "127.0.0.1",
    [switch]$SkipBootstrap,
    [switch]$NoBrowser,
    [string]$Date = "today"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Get-VenvRepairMessage {
    param([string]$PythonPath)

    return @"
Broken or missing virtualenv Python:
  $PythonPath

Rebuild it from PowerShell:
  py -3 -m venv .\.venv
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
"@
}

if (-not (Test-Path $Python)) {
    throw (Get-VenvRepairMessage -PythonPath $Python)
}

try {
    $PythonProbe = & $Python -c "import sys; print(sys.executable)" 2>&1
    $PythonProbeExitCode = $LASTEXITCODE
} catch {
    $PythonProbe = $_.Exception.Message
    $PythonProbeExitCode = 1
}
if ($PythonProbeExitCode -ne 0) {
    throw "$(Get-VenvRepairMessage -PythonPath $Python)`nPython probe failed:`n$PythonProbe"
}

try {
    $UvicornProbe = & $Python -c "import uvicorn; print(uvicorn.__name__)" 2>&1
    $UvicornProbeExitCode = $LASTEXITCODE
} catch {
    $UvicornProbe = $_.Exception.Message
    $UvicornProbeExitCode = 1
}
if ($UvicornProbeExitCode -ne 0) {
    throw "$(Get-VenvRepairMessage -PythonPath $Python)`nUvicorn import failed:`n$UvicornProbe"
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

$Url = "http://$BindHost`:$Port"
if (-not $NoBrowser) {
    Start-Process $Url
}

& $Python -m uvicorn mlb_app.asgi:app --host $BindHost --port $Port

