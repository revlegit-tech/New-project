# Windows Task Scheduler

Use the repository root as the task working directory:

```text
C:\Users\RevLe\OneDrive\Documents\New project
```

Suggested actions:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_actionnetwork_live_snapshot.ps1 -Date today
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run_daily_mlb_workflow.ps1 -Date today
```

Suggested schedule:

- Morning snapshot: 9:30 AM ET.
- Midday snapshot: 12:30 PM ET.
- Afternoon snapshot: 3:30 PM ET.
- Near-close snapshot: 6:30 PM ET.
- Postgame workflow: overnight after final MLB logs are expected.

The wrappers use lock files under `data/status/` to prevent overlap and recover stale locks. Status JSON is generated under `data/status/` and is intentionally ignored by git.
