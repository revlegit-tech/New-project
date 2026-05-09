# Phase 19 Patch

Adds observed line movement tracking for game context.

Apply and validate:

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase19_line_movement_tracking_artifacts.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python -m py_compile tools/phase19_line_movement.py tools/run_phase19_line_movement.py tools/phase19_line_movement_qa.py tools/apply_phase19_collector_hook.py tools/apply_phase19_ui_movement_patch.py
python -m pytest tests/test_phase19_line_movement.py -q
```
