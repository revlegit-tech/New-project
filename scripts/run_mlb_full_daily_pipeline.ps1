param(
  [string]$Date = "today",
  [int]$Season = 2026,
  [string]$Base = "http://127.0.0.1:8765",
  [int]$BoardLimit = 5000,
  [switch]$SkipGithubImport
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

function Test-App {
  try {
    $tcp = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if (-not $tcp) {
      return $false
    }

    Invoke-WebRequest "$Base/docs" -TimeoutSec 10 -UseBasicParsing | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Start-App-IfNeeded {
  if (Test-App) {
    Write-Host "App already responding."
    return
  }

  Write-Host "App not responding. Starting FastAPI directly..."

  $startScript = Join-Path $Root "scripts\start_mlb_app.ps1"

  if (Test-Path $startScript) {
    Start-Process powershell.exe -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy", "Bypass",
      "-NoExit",
      "-File", "`"$startScript`"",
      "-Port", "8765",
      "-BindHost", "127.0.0.1",
      "-SkipBootstrap",
      "-NoBrowser",
      "-Date", "$RunDate"
    ) -WorkingDirectory $Root
  } else {
    Start-Process powershell.exe -ArgumentList @(
      "-NoProfile",
      "-ExecutionPolicy", "Bypass",
      "-NoExit",
      "-Command",
      "cd `"$Root`"; `$env:PYTHONPATH=`"$Root`"; `$env:DB_ENABLED='1'; `$env:DB_FALLBACK_TO_CSV='1'; .\.venv\Scripts\python.exe -m uvicorn mlb_app.asgi:app --host 127.0.0.1 --port 8765"
    ) -WorkingDirectory $Root
  }

  for ($i = 1; $i -le 180; $i++) {
    Start-Sleep -Seconds 2

    if (Test-App) {
      Write-Host "App is responding."
      return
    }

    Write-Host "Waiting for app... attempt $i"
  }

  throw "App did not respond at $Base. Check the separate app PowerShell window for the real startup error."
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



