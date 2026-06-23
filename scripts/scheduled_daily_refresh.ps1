$ErrorActionPreference = "Continue"

$Root = "C:\Users\RevLe\OneDrive\Documents\New project"
$LogDir = Join-Path $Root "data\logs\scheduler"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $LogDir "daily_refresh_$Stamp.log"

Set-Location $Root

"[$(Get-Date -Format o)] Starting daily refresh" | Tee-Object -FilePath $Log -Append
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_daily_mlb_workflow.ps1" -Date today *>> $Log
$Code = $LASTEXITCODE
"[$(Get-Date -Format o)] Finished daily refresh with exit code $Code" | Tee-Object -FilePath $Log -Append

exit $Code
