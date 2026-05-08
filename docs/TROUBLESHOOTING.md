# Troubleshooting

## Server starts but UI data looks stale

Check:

```bash
curl http://127.0.0.1:8765/api/app/status
python tools/validate_data_contracts.py --root . --season 2026
```

Confirm the latest odds/playerboard date is distinct from the latest fully graded date.

## Safe export fails

The exporter refuses to include secret-like filenames and values. Remove local env files from the export root, rotate any exposed keys, and rerun:

```bash
python tools/export_project.py --output dist/mlb-app-source.zip
```

## Contract tests fail

A route response shape changed. Either restore the stable field or update `docs/API_CONTRACTS.md` and the corresponding test deliberately.

## Type checks fail in legacy files

The current type gate intentionally targets `mlb_app/`. Do not widen mypy to the legacy monolith until the route family being migrated has schemas and services.

## Playwright cannot start

Install browser dependencies:

```bash
npm install
npm run install:browsers
npm run test:e2e
```
