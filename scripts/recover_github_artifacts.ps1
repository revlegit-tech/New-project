param(
    [string]$Repo = "revlegit-tech/New-project",
    [string]$Workflow = "season-collector.yml",
    [datetime]$StartDate = [datetime]"2026-05-09",
    [datetime]$EndDate = (Get-Date),
    [int]$Limit = 300
)

$ErrorActionPreference = "Continue"

$ProjectRoot = (Get-Location).Path
$DownloadRoot = Join-Path $ProjectRoot "github_artifacts"
$ExtractRoot = Join-Path $ProjectRoot "github_artifacts_extracted"
$ImportRoot = Join-Path $ProjectRoot "data\artifact_imports"
$HealthRoot = Join-Path $ProjectRoot "data\health"
$ManifestPath = Join-Path $HealthRoot "artifact_recovery_manifest.csv"

New-Item -ItemType Directory -Force $DownloadRoot, $ExtractRoot, $ImportRoot, $HealthRoot | Out-Null

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GitHub CLI (gh) was not found. Install/authenticate gh before running recovery." -ForegroundColor Red
    exit 1
}

Write-Host "Repo: $Repo" -ForegroundColor Cyan
Write-Host "Workflow: $Workflow" -ForegroundColor Cyan
Write-Host "Date range: $($StartDate.ToString("yyyy-MM-dd")) -> $($EndDate.ToString("yyyy-MM-dd"))" -ForegroundColor Cyan
Write-Host ""

Write-Host "Reading GitHub Actions runs..." -ForegroundColor Cyan

$runsJson = gh run list `
  --repo $Repo `
  --workflow $Workflow `
  --limit $Limit `
  --json databaseId,createdAt,displayTitle,status,conclusion 2>$null

if (-not $runsJson) {
    Write-Host "No runs returned. Check gh auth status and workflow name." -ForegroundColor Red
    exit 1
}

$runs = $runsJson | ConvertFrom-Json

$runs = $runs | Where-Object {
    $created = [datetime]$_.createdAt
    ($created -ge $StartDate) -and ($created -le $EndDate)
} | Sort-Object createdAt

Write-Host "Runs in range: $($runs.Count)" -ForegroundColor Green

$manifest = New-Object System.Collections.Generic.List[object]

function Get-FileKind {
    param([string]$Path, [string]$Name)

    $normalized = $Path -replace "/", "\"

    if ($Name -match "propline_props_2026-\d{2}-\d{2}.*\.csv") {
        return "raw_propline_props"
    }

    if ($normalized -match "\\data\\warehouse\\odds_snapshots\\" -and $Name -match "propline_props") {
        return "warehouse_propline_snapshot"
    }

    if ($normalized -match "\\data\\warehouse\\raw\\") {
        return "warehouse_raw"
    }

    if ($normalized -match "\\data\\warehouse\\summaries\\") {
        return "warehouse_summary"
    }

    if ($normalized -match "\\data\\warehouse\\logs\\") {
        return "warehouse_log"
    }

    if ($normalized -match "\\data\\odds\\") {
        return "odds_file"
    }

    if ($normalized -match "\\data\\playerboard\\" -and $Name -match "playerboard") {
        return "playerboard"
    }

    if ($normalized -match "\\data\\cache\\odds_movement\\") {
        return "odds_movement"
    }

    if ($normalized -match "\\data\\cloud\\summaries\\") {
        return "cloud_summary"
    }

    if ($normalized -match "\\data\\cloud\\season_logs\\") {
        return "season_log"
    }

    if ($normalized -match "\\data\\ml\\") {
        return "ml_training"
    }

    if ($normalized -match "\\data\\backtests\\") {
        return "backtest"
    }

    if ($normalized -match "\\data\\audit\\") {
        return "audit"
    }

    if ($normalized -match "\\data\\health\\collector_manifests\\" -or $Name -eq "latest_collector_manifest.json") {
        return "collector_manifest"
    }

    return "other"
}

function Expand-ArchivesRecursive {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )

    New-Item -ItemType Directory -Force $TargetDir | Out-Null
    $processed = @{}

    for ($pass = 1; $pass -le 5; $pass++) {
        $archives = Get-ChildItem $SourceDir, $TargetDir -Recurse -File -ErrorAction SilentlyContinue |
          Where-Object {
            $_.Name -match "\.zip$|\.tgz$|\.tar\.gz$"
          }

        foreach ($archive in $archives) {
            if ($processed.ContainsKey($archive.FullName)) {
                continue
            }

            $processed[$archive.FullName] = $true

            $safeName = ($archive.Name -replace "[^a-zA-Z0-9_.-]", "_")
            $outDir = Join-Path $TargetDir ("extract_pass{0}_{1}" -f $pass, $safeName)

            New-Item -ItemType Directory -Force $outDir | Out-Null

            try {
                if ($archive.Name -match "\.zip$") {
                    Expand-Archive $archive.FullName -DestinationPath $outDir -Force
                }
                elseif ($archive.Name -match "\.tgz$|\.tar\.gz$") {
                    tar -xzf $archive.FullName -C $outDir
                }

                Write-Host "Extracted: $($archive.Name)" -ForegroundColor DarkGray
            }
            catch {
                Write-Host "Could not extract: $($archive.FullName)" -ForegroundColor Yellow
                Write-Host $_.Exception.Message -ForegroundColor Yellow
            }
        }
    }
}

foreach ($run in $runs) {
    $runId = $run.databaseId
    $createdDate = ([datetime]$run.createdAt).ToString("yyyy-MM-dd")
    $label = "$createdDate-$runId"

    $runDownloadDir = Join-Path $DownloadRoot $label
    $runExtractDir = Join-Path $ExtractRoot $label
    $runImportDir = Join-Path $ImportRoot $label

    Write-Host ""
    Write-Host "========================================" -ForegroundColor DarkGray
    Write-Host "Run $runId / $createdDate / $($run.conclusion)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor DarkGray

    New-Item -ItemType Directory -Force $runDownloadDir, $runExtractDir, $runImportDir | Out-Null

    Write-Host "Downloading artifacts..." -ForegroundColor Cyan

    gh run download $runId --repo $Repo --dir $runDownloadDir 2>$null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "No artifact or download failed for run $runId" -ForegroundColor Yellow

        $manifest.Add([pscustomobject]@{
            runId = $runId
            runDate = $createdDate
            conclusion = $run.conclusion
            kind = "download_failed_or_no_artifact"
            fileName = ""
            relativePath = ""
            fullPath = ""
            length = 0
        })

        continue
    }

    Expand-ArchivesRecursive -SourceDir $runDownloadDir -TargetDir $runExtractDir

    $allFiles = Get-ChildItem $runDownloadDir, $runExtractDir -Recurse -File -ErrorAction SilentlyContinue

    $usefulFiles = $allFiles | Where-Object {
        $p = $_.FullName -replace "/", "\"
        ($p -match "\\data\\odds\\") -or
        ($p -match "\\data\\warehouse\\odds_snapshots\\") -or
        ($p -match "\\data\\warehouse\\raw\\") -or
        ($p -match "\\data\\warehouse\\summaries\\") -or
        ($p -match "\\data\\warehouse\\logs\\") -or
        ($p -match "\\data\\health\\") -or
        ($p -match "\\data\\playerboard\\") -or
        ($p -match "\\data\\cache\\odds_movement\\") -or
        ($p -match "\\data\\cloud\\summaries\\") -or
        ($p -match "\\data\\cloud\\season_logs\\") -or
        ($p -match "\\data\\ml\\") -or
        ($p -match "\\data\\backtests\\") -or
        ($p -match "\\data\\audit\\")
    }

    if (-not $usefulFiles -or $usefulFiles.Count -eq 0) {
        Write-Host "No useful data files found in run $runId" -ForegroundColor Yellow
    }

    foreach ($file in $usefulFiles) {
        $normalized = $file.FullName -replace "/", "\"
        $dataIndex = $normalized.IndexOf("\data\")

        if ($dataIndex -ge 0) {
            $relativeDataPath = $normalized.Substring($dataIndex + 1)
        }
        else {
            $relativeDataPath = $file.Name
        }

        $dest = Join-Path $runImportDir $relativeDataPath
        New-Item -ItemType Directory -Force (Split-Path $dest -Parent) | Out-Null
        Copy-Item $file.FullName $dest -Force

        $kind = Get-FileKind -Path $file.FullName -Name $file.Name

        $manifest.Add([pscustomobject]@{
            runId = $runId
            runDate = $createdDate
            conclusion = $run.conclusion
            kind = $kind
            fileName = $file.Name
            relativePath = $relativeDataPath
            fullPath = $dest
            length = $file.Length
        })
    }

    $proplineCount = ($manifest | Where-Object { $_.runId -eq $runId -and ($_.kind -eq "raw_propline_props" -or $_.kind -eq "warehouse_propline_snapshot") }).Count
    $playerboardCount = ($manifest | Where-Object { $_.runId -eq $runId -and $_.kind -eq "playerboard" }).Count

    Write-Host "Recovered files: $($usefulFiles.Count)" -ForegroundColor Green
    Write-Host "Raw/warehouse ProLine files: $proplineCount" -ForegroundColor Magenta
    Write-Host "Playerboard files: $playerboardCount" -ForegroundColor Magenta
}

$manifest | Export-Csv $ManifestPath -NoTypeInformation

Write-Host ""
Write-Host "DONE" -ForegroundColor Green
Write-Host "Manifest saved to: $ManifestPath" -ForegroundColor Cyan
Write-Host "Imported artifact data saved under: $ImportRoot" -ForegroundColor Cyan
Write-Host ""
Write-Host "Quick checks:" -ForegroundColor Yellow
Write-Host "Import-Csv `"$ManifestPath`" | Group-Object kind | Sort-Object Count -Descending | Format-Table Count, Name"
Write-Host "Import-Csv `"$ManifestPath`" | Where-Object { `$_.kind -match 'propline' } | Format-Table runDate, runId, kind, fileName, length -AutoSize"
