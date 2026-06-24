param(
  [string]$Project = "C:\Users\RevLe\OneDrive\Documents\New project",
  [string]$Python = ""
)

if (-not $Python) {
  $Python = Join-Path $Project ".venv\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
  throw "Missing project virtualenv Python: $Python"
}

$env:PYTHONPATH = $Project

# Final autonomous schedule:
# 06:00 ET -> current day: MLB + PropLine + weather + odds snapshot
# 12:00 ET -> current day: MLB + PropLine + weather + odds snapshot
# 00:00 ET -> previous day: final results + boxscores + logs + Savant

$Morning = "`"$Python`" `"$Project\season_auto_collector.py`" snapshot --run-type morning"
$Midday = "`"$Python`" `"$Project\season_auto_collector.py`" snapshot --run-type midday"
$Midnight = "`"$Python`" `"$Project\season_auto_collector.py`" snapshot --run-type midnight --date-offset -1 --include-savant"

schtasks /Create /TN "Baseball Data Collector - 06AM ET" /SC DAILY /ST 06:00 /F /TR $Morning
schtasks /Create /TN "Baseball Data Collector - 12PM ET" /SC DAILY /ST 12:00 /F /TR $Midday
schtasks /Create /TN "Baseball Data Collector - 12AM ET" /SC DAILY /ST 00:00 /F /TR $Midnight

Write-Host ""
Write-Host "Final autonomous collector tasks created:"
Write-Host "- 06:00 ET: current-day snapshot"
Write-Host "- 12:00 ET: current-day snapshot"
Write-Host "- 00:00 ET: previous-day final snapshot + Savant"
Write-Host ""
Write-Host "Compact cloud-safe data:"
Write-Host "$Project\data\cloud"
Write-Host ""
Write-Host "Large local warehouse data:"
Write-Host "$Project\data\warehouse"
