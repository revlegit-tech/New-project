$ErrorActionPreference = "Continue"

$Root = "C:\Users\RevLe\OneDrive\Documents\New project"
$LogDir = Join-Path $Root "data\logs\scheduler"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $LogDir "actionnetwork_snapshot_$Stamp.log"

Set-Location $Root

"[$(Get-Date -Format o)] Starting ActionNetwork snapshot" | Tee-Object -FilePath $Log -Append
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_actionnetwork_live_snapshot.ps1" -Date today *>> $Log
$Code = $LASTEXITCODE
"[$(Get-Date -Format o)] Finished ActionNetwork snapshot with exit code $Code" | Tee-Object -FilePath $Log -Append

exit $Code
