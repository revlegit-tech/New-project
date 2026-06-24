param(
    [string]$Date = "today",
    [string]$RunType = "manual"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python virtual environment not found at $Python"
    exit 1
}

if (-not $env:PYTHONPATH) {
    $env:PYTHONPATH = $Root.Path
}

Set-Location $Root

$ResolvedDate = $Date
if ($Date -eq "today") {
    $ResolvedDate = Get-Date -Format "yyyy-MM-dd"
}

$LogDir = Join-Path $Root "data\logs\manual"
New-Item -ItemType Directory -Force $LogDir | Out-Null

$LogFile = Join-Path $LogDir "full_snapshot_$ResolvedDate.log"
$env:PLAYERBOARD_BUILD_WORKERS = if ($env:PLAYERBOARD_BUILD_WORKERS) { $env:PLAYERBOARD_BUILD_WORKERS } else { "1" }
$env:PLAYERBOARD_DAILY_BUILD_LIMIT = if ($env:PLAYERBOARD_DAILY_BUILD_LIMIT) { $env:PLAYERBOARD_DAILY_BUILD_LIMIT } else { "1000" }
$env:PLAYERBOARD_DAILY_SOURCE_MODE = if ($env:PLAYERBOARD_DAILY_SOURCE_MODE) { $env:PLAYERBOARD_DAILY_SOURCE_MODE } else { "propline" }

Write-Host "Running full MLB snapshot for $ResolvedDate..."
Write-Host "Log: $LogFile"

& $Python "season_auto_collector.py" "snapshot" "--date" $ResolvedDate "--run-type" $RunType *>&1 |
    Tee-Object -FilePath $LogFile

$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    & $Python "daily_ml_workflow.py" "run-daily" "--date" $ResolvedDate *>&1 |
        Tee-Object -FilePath $LogFile -Append
    $ExitCode = $LASTEXITCODE
}

$GameContextDir = Join-Path $Root "data\warehouse\game_context"
if (Test-Path $GameContextDir) {
    Get-ChildItem $GameContextDir -Filter "*.phase22v3_backup_*" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

if ($ExitCode -ne 0) {
    Write-Error "Full MLB snapshot failed with exit code $ExitCode"
}

exit $ExitCode
