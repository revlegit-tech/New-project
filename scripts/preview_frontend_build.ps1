$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendRoot = Join-Path $RepoRoot "frontend"
$BuildRoot = if (Test-Path (Join-Path $FrontendRoot "package.json")) { $FrontendRoot } else { $RepoRoot }

Push-Location $BuildRoot
try {
  Write-Host "Running npm run build from $BuildRoot"
  npm run build
}
finally {
  Pop-Location
}

$IndexPath = Join-Path $RepoRoot "public\index.html"
if (Test-Path $IndexPath) {
  $IndexHtml = Get-Content -LiteralPath $IndexPath -Raw
  $Match = [regex]::Match($IndexHtml, "/assets/outlier-[^`"']+\.js")
  if ($Match.Success) {
    Write-Host "Current outlier asset: $($Match.Value)"
  }
  else {
    Write-Host "Current outlier asset: not found in public/index.html"
  }
}
else {
  Write-Host "public/index.html not found."
}

Write-Host ""
Write-Host "Restart uvicorn if it is already running, open http://127.0.0.1:8765, then hard refresh with Ctrl+Shift+R."
Write-Host "Do not run git restore on public/index.html, public/.vite/manifest.json, or public/legacy.html until after preview."
