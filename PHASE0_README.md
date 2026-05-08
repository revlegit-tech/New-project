# Phase 0 Canonical Runtime Starter Artifacts

Copy these files into the project root:

- `Makefile` -> replace the current root `Makefile`.
- `Dockerfile` -> replace the current root `Dockerfile`.
- `mlb_app/wsgi.py` -> new production WSGI entrypoint for Gunicorn.
- `tools/safe_export.py` -> new strict source-only export script. You can replace or wrap `tools/export_project.py` with it.
- `docs/ENDPOINT_TRIAGE_TEMPLATE.md` and `docs/endpoint_triage_template.csv` -> endpoint inventory worksheet.
- `requirements.phase0-addition.txt` -> add the listed dependency to `requirements.txt`.
- `app_py_legacy_banner.txt` -> paste at the top of `app.py`, below any module docstring only if one already exists.

Phase 0 validation commands:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
make run
make health
make serve
python tools/safe_export.py --output dist/mlb-app-source.zip --max-mb 25
```

The canonical runtime is now `mlb_app`; `app.py` is legacy-only through `make run-legacy`.
