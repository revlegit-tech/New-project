[CmdletBinding()]
param(
  [switch]$InstallPyInstaller,
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$LauncherSource = Join-Path $Root "tools\windows_launcher.py"

if (!(Test-Path $Python)) {
  throw "Missing .venv Python: $Python"
}

if (!(Test-Path $LauncherSource)) {
  throw "Missing launcher source: $LauncherSource"
}

if ($InstallPyInstaller) {
  & $Python -m pip install pyinstaller
}

if ($Clean) {
  foreach ($Path in @("build\windows_launcher", "dist\windows_launcher")) {
    Remove-Item -Recurse -Force $Path -ErrorAction SilentlyContinue
  }
}

& $Python -m PyInstaller `
  --onefile `
  --name MLBPropLauncher `
  --console `
  --clean `
  --specpath build\windows_launcher `
  --workpath build\windows_launcher `
  --distpath dist\windows_launcher `
  tools\windows_launcher.py

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Built launcher:" -ForegroundColor Green
Write-Host "  $Root\dist\windows_launcher\MLBPropLauncher.exe"
Write-Host ""
Write-Host "Double-click it, or run:"
Write-Host "  .\dist\windows_launcher\MLBPropLauncher.exe"
