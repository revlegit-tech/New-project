# Local Launcher EXE Plan

A future EXE should be a tiny Windows wrapper that calls:

```powershell
.\scripts\start_mlb_app.ps1
```

It should not bundle the full FastAPI app, Python environment, ML models, generated data, or collectors. The wrapper can provide a double-click entry point, choose a port, and show basic bootstrap/server status.

The source of truth remains the PowerShell launcher and the repository-managed virtual environment.
