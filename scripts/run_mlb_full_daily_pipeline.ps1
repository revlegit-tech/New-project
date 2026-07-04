param(
  [string]$Date = "today",
  [int]$Season = 2026,
  [string]$Base = "http://127.0.0.1:8765",
  [int]$BoardLimit = 5000,
  [switch]$SkipGithubImport,
  [switch]$ForcePortRelease
)

$ErrorActionPreference = "Stop"

$Root = "C:\Users\RevLe\OneDrive\Documents\New project"
$Repo = "revlegit-tech/New-project"

Set-Location $Root

if ($Date -eq "today") {
  $RunDate = Get-Date -Format "yyyy-MM-dd"
} else {
  $RunDate = $Date
}

try {
  $BaseUri = [System.UriBuilder]::new($Base)
  $BaseUri.Host = "127.0.0.1"
  $Base = $BaseUri.Uri.GetLeftPart([System.UriPartial]::Authority)
} catch {
  $Base = "http://127.0.0.1:8765"
}

$env:PYTHONPATH = $Root
$env:PLAYERBOARD_BUILD_WORKERS = "1"
$env:BASEBALL_PROP_APP_URL = $Base

Write-Host "==========================================="
Write-Host "REVLEGIT MLB FULL DAILY PIPELINE"
Write-Host "Date: $RunDate"
Write-Host "Season: $Season"
Write-Host "BoardLimit: $BoardLimit"
Write-Host "Base: $Base"
Write-Host "==========================================="

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Block,
    [switch]$ContinueOnError
  )

  Write-Host ""
  Write-Host "[$Name]"
  Write-Host ("-" * ($Name.Length + 2))

  try {
    & $Block
    Write-Host "OK: $Name"
  } catch {
    Write-Host "FAILED: $Name"
    Write-Host $_.Exception.Message

    if (-not $ContinueOnError) {
      throw
    }
  }
}

function Get-AppPort {
  try {
    return [int]([System.Uri]$Base).Port
  } catch {
    return 8765
  }
}

function Get-ListenPortOwners {
  param([int]$Port = 8765)

  $owners = @()

  try {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Where-Object { $_.OwningProcess -and [int]$_.OwningProcess -ne 0 }
    foreach ($connection in @($connections)) {
      $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
      $name = if ($process) { $process.ProcessName } else { "unknown" }
      $owners += [pscustomobject]@{
        Pid = [int]$connection.OwningProcess
        ProcessName = $name
        LocalAddress = $connection.LocalAddress
        LocalPort = [int]$connection.LocalPort
      }
    }
  } catch {
  }

  if ($owners.Count -gt 0) {
    return $owners
  }

  try {
    $pattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in @(netstat -ano | Select-String -Pattern $pattern)) {
      if ($line.Line -match $pattern) {
        $pidValue = [int]$matches[1]
        if ($pidValue -eq 0) {
          continue
        }
        $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        $name = if ($process) { $process.ProcessName } else { "unknown" }
        $owners += [pscustomobject]@{
          Pid = $pidValue
          ProcessName = $name
          LocalAddress = "unknown"
          LocalPort = $Port
        }
      }
    }
  } catch {
  }

  return $owners
}

function Get-PortOwnerSummary {
  param([int]$Port = 8765)

  $owners = @(Get-ListenPortOwners -Port $Port)
  if ($owners.Count -gt 0) {
    return (($owners | ForEach-Object { "pid=$($_.Pid) process=$($_.ProcessName) local=$($_.LocalAddress):$($_.LocalPort)" }) -join "; ")
  }

  return "none"
}

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

function Test-VenvReady {
  $python = Join-Path $Root ".venv\Scripts\python.exe"

  if (-not (Test-Path $python)) {
    throw (Get-VenvRepairMessage -PythonPath $python)
  }

  try {
    $probe = & $python -c "import sys; print(sys.executable)" 2>&1
    $probeExitCode = $LASTEXITCODE
  } catch {
    $probe = $_.Exception.Message
    $probeExitCode = 1
  }
  if ($probeExitCode -ne 0) {
    throw "$(Get-VenvRepairMessage -PythonPath $python)`nPython probe failed:`n$probe"
  }

  try {
    $uvicornProbe = & $python -c "import uvicorn; print(uvicorn.__name__)" 2>&1
    $uvicornExitCode = $LASTEXITCODE
  } catch {
    $uvicornProbe = $_.Exception.Message
    $uvicornExitCode = 1
  }
  if ($uvicornExitCode -ne 0) {
    throw "$(Get-VenvRepairMessage -PythonPath $python)`nUvicorn import failed:`n$uvicornProbe"
  }

  return $python
}

function Invoke-AppHealthProbe {
  param(
    [switch]$AllowDocsFallback
  )

  $probes = @("/api/health")
  if ($AllowDocsFallback) {
    $probes += "/docs"
  }

  $last = [ordered]@{
    healthy = $false
    endpoint = ""
    statusCode = $null
    error = "No health probe attempted."
  }

  foreach ($path in $probes) {
    $uri = "$Base$path"
    $last.endpoint = $uri
    try {
      $response = Invoke-WebRequest $uri -TimeoutSec 10 -UseBasicParsing
      $last.statusCode = [int]$response.StatusCode
      $last.error = ""
      if ([int]$response.StatusCode -eq 200) {
        $last.healthy = $true
        return [pscustomobject]$last
      }
    } catch {
      $last.statusCode = $null
      if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
        $last.statusCode = [int]$_.Exception.Response.StatusCode
      }
      $last.error = $_.Exception.Message
    }
  }

  return [pscustomobject]$last
}

function Test-App {
  param(
    [switch]$AllowDocsFallback
  )

  return (Invoke-AppHealthProbe -AllowDocsFallback:$AllowDocsFallback).healthy
}

function Invoke-OptionalModelStatusProbe {
  $uri = "$Base/api/ml-models/status"
  try {
    $response = Invoke-WebRequest $uri -TimeoutSec 10 -UseBasicParsing
    Write-Host "Model status probe ok at $uri (HTTP $([int]$response.StatusCode))."
  } catch {
    Write-Host "WARNING: Optional model status probe failed at ${uri}: $($_.Exception.Message)"
  }
}

function Start-App-IfNeeded {
  $Port = Get-AppPort
  $python = Test-VenvReady
  $health = Invoke-AppHealthProbe
  if ($health.healthy) {
    Write-Host "App already healthy at $($health.endpoint) (HTTP $($health.statusCode))."
    Invoke-OptionalModelStatusProbe
    return
  }

  $owner = Get-PortOwnerSummary -Port $Port
  if ($owner -ne "none") {
    if (-not $ForcePortRelease) {
      Write-Host "Port $Port has active LISTEN process(es): $owner"
      throw "App is not healthy at $Base and the port has an active listener. Last readiness probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error). Use -ForcePortRelease only when you intentionally want this script to stop those listener process(es)."
    }

    Write-Host "ForcePortRelease set. Stopping active LISTEN process(es) on port ${Port}: $owner"
    foreach ($listener in @(Get-ListenPortOwners -Port $Port)) {
      Stop-Process -Id $listener.Pid -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
  }

  Write-Host "App not responding. Starting FastAPI directly..."

  $outLog = Join-Path $Root "server-8765.log"
  $errLog = Join-Path $Root "server-8765.err.log"
  $env:DB_ENABLED = "1"
  $env:DB_FALLBACK_TO_CSV = "1"
  $process = Start-Process -FilePath $python -ArgumentList @(
    "-m",
    "uvicorn",
    "mlb_app.asgi:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$Port"
  ) -WorkingDirectory $Root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru

  for ($i = 1; $i -le 180; $i++) {
    Start-Sleep -Seconds 2

    $health = Invoke-AppHealthProbe
    if ($health.healthy) {
      Write-Host "App is healthy at $($health.endpoint) (HTTP $($health.statusCode))."
      Invoke-OptionalModelStatusProbe
      return
    }

    if ($process.HasExited) {
      $owner = Get-PortOwnerSummary -Port $Port
      throw "App process exited during startup. Last readiness probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error). Port $Port owner: $owner. Logs: $outLog $errLog"
    }

    Write-Host "Waiting for app... attempt $i. Last probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error)"
  }

  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
  $owner = Get-PortOwnerSummary -Port $Port
  throw "App did not become healthy at $Base. Last readiness probe: endpoint=$($health.endpoint) status=$($health.statusCode) error=$($health.error). Port $Port owner: $owner. Logs: $outLog $errLog"
}

function Invoke-ContextSourceMaterialization {
  $script = Join-Path $Root "scripts\materialize_context_sources.py"
  if (-not (Test-Path $script)) {
    Write-Host "WARNING: context source script missing; continuing without optional context artifacts."
    Write-Host "WARNING: context source partial."
    return
  }

  & .\.venv\Scripts\python.exe $script --date $RunDate --season $Season
  if ($LASTEXITCODE -ne 0) {
    throw "Context source materialization failed with exit code $LASTEXITCODE"
  }

  $auditPath = Join-Path $Root "data\context\context_source_audit_$RunDate.json"
  if (-not (Test-Path $auditPath)) {
    Write-Host "WARNING: context source audit missing after materialization; continuing with available artifacts."
    Write-Host "WARNING: context source partial."
    return
  }

  $audit = Get-Content -LiteralPath $auditPath -Raw | ConvertFrom-Json
  Write-Host "Context audit: $auditPath"
  Write-Host "Ready feature groups: $(@($audit.readyFeatureGroups) -join ', ')"
  Write-Host "Missing feature groups: $(@($audit.missingFeatureGroups) -join ', ')"
  Write-Host "externalApiCallsMade=$($audit.externalApiCallsMade) pregameSafe=$($audit.pregameSafe) labelsExcluded=$($audit.labelsExcluded)"

  foreach ($warning in @($audit.warnings)) {
    Write-Host "WARNING: $warning"
  }
  if (@($audit.missingFeatureGroups) -contains "weather") {
    Write-Host "WARNING: weather unavailable."
  }
  if ($audit.providerStatuses.umpire -eq "neutral_fallback") {
    Write-Host "WARNING: umpire neutral fallback."
  }
  if (@($audit.missingFeatureGroups) -contains "game_markets") {
    Write-Host "WARNING: game markets missing."
  }
  if (@($audit.missingFeatureGroups).Count -gt 0 -or @($audit.warnings).Count -gt 0) {
    Write-Host "WARNING: context source partial."
  }
}

function Import-GithubCollectorArtifact {
  if ($SkipGithubImport) {
    Write-Host "Skipping GitHub collector import."
    return
  }

  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GitHub CLI not found. Skipping GitHub collector import."
    return
  }

  $RunId = gh run list `
    --repo $Repo `
    --workflow "Baseball data collector" `
    --status success `
    --limit 1 `
    --json databaseId `
    --jq ".[0].databaseId"

  if (-not $RunId) {
    Write-Host "No successful GitHub collector run found. Skipping import."
    return
  }

  Write-Host "Latest successful GitHub collector run: $RunId"

  $StageRoot = Join-Path $env:TEMP "revlegit_mlb_github_collector_imports"
  $RunDir = Join-Path $StageRoot $RunId
  $ExtractDir = Join-Path $RunDir "extracted"

  Remove-Item $RunDir -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
  New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

  gh run download $RunId --repo $Repo --dir $RunDir

  $Tgz = Get-ChildItem $RunDir -Recurse -Filter "*.tgz" | Select-Object -First 1

  if (-not $Tgz) {
    Write-Host "No .tgz artifact found for run $RunId. Skipping import."
    return
  }

  tar -xzf $Tgz.FullName -C $ExtractDir

  $SourceData = Join-Path $ExtractDir "data"

  if (-not (Test-Path $SourceData)) {
    Write-Host "Extracted artifact has no data folder. Skipping import."
    return
  }

  $SafeFolders = @(
    "odds",
    "warehouse\odds_snapshots",
    "warehouse\raw",
    "warehouse\summaries",
    "warehouse\normalized",
    "health",
    "edge_board"
  )

  foreach ($Folder in $SafeFolders) {
    $Source = Join-Path $SourceData $Folder
    $Dest = Join-Path (Join-Path $Root "data") $Folder

    if (Test-Path $Source) {
      Write-Host "Merging GitHub artifact folder: data\$Folder"
      New-Item -ItemType Directory -Force -Path $Dest | Out-Null

      robocopy $Source $Dest /E /XO /R:2 /W:2 /NFL /NDL /NJH /NJS | Out-Host

      if ($LASTEXITCODE -gt 7) {
        throw "Robocopy failed for data\$Folder with exit code $LASTEXITCODE"
      }
    }
  }

  Write-Host "GitHub collector import complete."
}

Invoke-Step "Start app if needed" {
  Start-App-IfNeeded
}

Invoke-Step "Local PropLine daily pull" {
  $Markets = @(
    "pitcher_strikeouts",
    "batter_hits",
    "batter_total_bases",
    "batter_home_runs",
    "batter_rbis",
    "batter_stolen_bases",
    "batter_walks",
    "batter_singles",
    "batter_doubles",
    "batter_runs",
    "batter_2plus_hits",
    "batter_2plus_home_runs",
    "batter_2plus_rbis",
    "batter_3plus_rbis",
    "pitcher_outs",
    "pitcher_hits_allowed",
    "pitcher_earned_runs"
  ) -join ","

  $EncodedMarkets = [System.Uri]::EscapeDataString($Markets)
  $EncodedDate = [System.Uri]::EscapeDataString($RunDate)

  $Uri = "$Base/api/admin/propline/props/sync?markets=$EncodedMarkets&date=$EncodedDate"

  $payload = Invoke-RestMethod `
    -Method Post `
    -Uri $Uri `
    -Headers @{ "X-Baseball-Prop-Action" = "1" } `
    -TimeoutSec 180

  $payload | ConvertTo-Json -Depth 8
}


Invoke-Step "GitHub collector artifact import" {
  Import-GithubCollectorArtifact
} -ContinueOnError

Invoke-Step "ActionNetwork snapshot" {
  $ActionScript = Join-Path $Root "scripts\run_actionnetwork_live_snapshot.ps1"

  if (Test-Path $ActionScript) {
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ActionScript -Date $RunDate
  } else {
    Write-Host "ActionNetwork snapshot script not found. Skipping."
  }
} -ContinueOnError

Invoke-Step "Direct playerboard build" {
  $code = @"
from mlb_app.services.playerboard_builder import build_playerboard
import json, time

print("starting direct playerboard build", flush=True)
started = time.time()

payload = build_playerboard(
    season=$Season,
    date_label="$RunDate",
    market="",
    limit=$BoardLimit,
    save=True,
    replace_date=True,
    source_mode="propline",
)

print("elapsed:", round(time.time() - started, 2), flush=True)
print(json.dumps({
    "date": payload.get("date"),
    "propsLoaded": payload.get("propsLoaded"),
    "cardsBuilt": payload.get("cardsBuilt"),
    "saved": payload.get("saved"),
    "errors": payload.get("errors", [])[:10],
}, indent=2, default=str), flush=True)
"@

  $code | .\.venv\Scripts\python.exe -
}

Invoke-Step "Context source materialization" {
  Invoke-ContextSourceMaterialization
}

Invoke-Step "Playerboard-safe model scoring" {
  .\.venv\Scripts\python.exe .\scripts\score_player_prop_models.py `
    --date $RunDate `
    --season $Season `
    --source playerboard
}

Invoke-Step "Feature matrix materialization" {
  $code = @"
from pathlib import Path
import json

from mlb_app.config import Settings
from mlb_app.services.feature_store_materializer import FeatureStoreMaterializer

root = Path.cwd()
settings = Settings.from_env(root)

payload = FeatureStoreMaterializer(settings).materialize(
    date_label="$RunDate",
    season=$Season,
    limit=$BoardLimit,
)

print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
"@

  $code | .\.venv\Scripts\python.exe -
}

Invoke-Step "Collector check" {
  Invoke-RestMethod "$Base/api/runtime/collector-check?date=$RunDate" |
    ConvertTo-Json -Depth 10
}

Invoke-Step "Daily health" {
  Invoke-RestMethod "$Base/api/runtime/daily-health?date=$RunDate&season=$Season" |
    ConvertTo-Json -Depth 12
}

Invoke-Step "Row count summary" {
  $propsPath = ".\data\odds\propline_props_$RunDate.csv"
  $featurePath = ".\data\features\prop_features_$RunDate.csv"
  $playerboardPath = ".\data\playerboard\playerboard_$Season.csv"

  Write-Host "Date: $RunDate"

  if (Test-Path $propsPath) {
    $propsCount = (Import-Csv $propsPath | Measure-Object).Count
    Write-Host "Raw PropLine props: $propsCount"
  } else {
    Write-Host "Raw PropLine props: MISSING"
  }

  if (Test-Path $featurePath) {
    $featureCount = (Import-Csv $featurePath | Measure-Object).Count
    Write-Host "Feature rows: $featureCount"
  } else {
    Write-Host "Feature rows: MISSING"
  }

  if (Test-Path $playerboardPath) {
    $boardCount = (Import-Csv $playerboardPath | Where-Object { $_.date -eq $RunDate } | Measure-Object).Count
    Write-Host "Saved playerboard rows for date: $boardCount"
  } else {
    Write-Host "Playerboard file: MISSING"
  }
}

Invoke-Step "Generated artifact hygiene checks" {
  .\.venv\Scripts\python.exe .\tools\validate_generated_artifacts.py --root .
  .\.venv\Scripts\python.exe .\tools\validate_backup_files.py --root .
} -ContinueOnError

Write-Host ""
Write-Host "==========================================="
Write-Host "PIPELINE COMPLETE"
Write-Host "==========================================="



