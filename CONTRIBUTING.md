# Contributing

This app is being hardened into a premium MLB betting research product. Contributions should improve trust, safety, maintainability, or bettor-facing clarity.

## Before opening a PR

Run:

```bash
make security
make lint
make typecheck
make test
make test-contracts
```

For UI changes, also run:

```bash
make test-ui
```

## Backend standards

- Keep endpoint URLs stable during migration.
- Route handlers should be thin.
- Business rules belong in `mlb_app/services/`.
- File access belongs in `mlb_app/repositories/`.
- Response shapes belong in `mlb_app/schemas/` and contract tests.
- Betting model validation must be chronological, never random, unless the code is explicitly marked as research-only.

## Security standards

- Never commit `.env`, `.en`, private keys, tokens, screenshots with secrets, generated model artifacts, or local data caches.
- Use `tools/export_project.py` for shareable source zips.
- Treat any leaked provider key as compromised and rotate it.

## UI standards

The product direction is a dark, data-rich “Bloomberg Terminal for Bettors” experience. Dense views are acceptable only when hierarchy, status, and trust context remain obvious.

Avoid confident betting language unless the market has model readiness, grading history, calibration, and risk controls.
