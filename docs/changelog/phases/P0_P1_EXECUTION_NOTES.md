# P0/P1 Backend + Security Execution Notes

This branch applies the first non-breaking slice of the audit roadmap.

## What changed

- Removed the local `.en` file from the working tree. If it was ever tracked, run `git rm --cached .en` and rotate the exposed key.
- Hardened `.gitignore` for `.env`, `.en`, key, PEM, and secret-like files.
- Added `tools/security_preflight.py` to fail CI if secret-bearing filenames are tracked.
- Added `tools/export_project.py` for reproducible safe source exports.
- Added `.pre-commit-config.yaml` with a local security preflight and detect-secrets hook.
- Updated CI to run security preflight, pytest, and gitleaks.
- Added a transitional `mlb_app/` package to avoid breaking `app.py` while creating the target service architecture.
- Added explicit router, HTTP helpers, repositories, services, schemas, and model-readiness service.
- Changed `/api/prop-ml/status` to report exact market-artifact readiness through `ModelRegistryService`.
- Disabled silent generic prop-model fallback for production predictions. A generic fallback now requires `MLB_ALLOW_GENERIC_PROP_MODEL_FALLBACK=1`.
- Added chronological train/validation split utilities and leakage-column guardrails.
- Added tests for safe export, model readiness, router dispatch, and chronological validation.

## Validation run

```bash
python -m pytest -q
# 49 passed

python tools/export_project.py --output dist/mlb-app-source.zip
# produces a source-only zip excluding local secrets and generated data
```

## Required manual actions

1. Rotate any key that was present in `.env`, `.en`, or shared archives.
2. If this repo has a remote history containing secrets, rewrite/purge that history before pushing.
3. Run `git rm --cached .en` if `.en` is tracked.
4. Copy `config/model_registry.example.json` to `data/models/model_registry.json` when real market-specific artifacts are available.
5. Keep `app.py` as the legacy bootstrap during migration; move routes into `mlb_app/routes`, logic into `mlb_app/services`, file IO into `mlb_app/repositories`, and response contracts into `mlb_app/schemas`.
