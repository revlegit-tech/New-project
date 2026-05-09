# Phase 18 v8 — Missing `re` Import Fix

The Phase 18 v7 EdgeBoard context join helper uses `re.sub(...)` to normalize team names/abbreviations. If `mlb_app/services/edge_board_service.py` does not import `re`, direct QA fails with:

```text
NameError: name 're' is not defined
```

Run:

```powershell
python .\tools\phase18_v8_fix_missing_re_import.py
python -m py_compile playerboard.py mlb_app/services/edge_board_service.py mlb_app/services/prop_detail_service.py season_auto_collector.py tools/phase18_context_qa.py
```
