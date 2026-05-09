# Phase 20 UI Polish + Audit Cleanup

Apply this patch after Phase 19.

```powershell
cd "C:\Users\RevLe\OneDrive\Documents\New project"
Expand-Archive "$env:USERPROFILE\Downloads\phase20_ui_polish_audit_cleanup_artifacts.zip" -DestinationPath . -Force
$env:PYTHONPATH = (Get-Location).Path
python .\tools\apply_phase20_ui_and_audit_polish.py
python -m py_compile tools/apply_phase20_ui_and_audit_polish.py tools/phase20_audit_cleanup_qa.py tools/phase16_common.py tools/phase16_live_feature_audit.py tools/phase17_game_context_audit.py
python -m pytest tests/test_phase20_ui_and_audit_polish.py -q
```

QA:

```powershell
$Date = "2026-05-07"
python .\tools\phase20_audit_cleanup_qa.py --date $Date --market batter_hits
python -m mlb_app.server 8765 --host 127.0.0.1
```

Open `http://127.0.0.1:8765/?view=outlier`, click a prop, and inspect the Game Context rail.
