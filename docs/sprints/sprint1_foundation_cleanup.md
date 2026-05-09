# Sprint 1 — Foundation Cleanup Implementation Summary

## Completed

- Added `ARCHITECTURE.md` and linked it from `README.md`.
- Added `ROADMAP.md` with Sprint 1 exit criteria and Sprint 2 handoff.
- Split dependencies into `requirements/base.in`, `requirements/ml.in`, and `requirements/dev.in`.
- Generated deterministic `uv` lockfiles for Python 3.12:
  - `requirements/base.lock.txt`
  - `requirements/ml.lock.txt`
  - `requirements/dev.lock.txt`
- Updated Docker, Makefile, GitHub Actions, and devcontainer installs to use lockfiles.
- Archived phase/stage notes and patch artifacts under `docs/changelog/`.
- Moved root diagnostics into `tools/diagnostics/`.
- Archived one-time patch scripts under `docs/changelog/patches/one_time_scripts/`.
- Removed generated/in-tree backup files from `mlb_app`, `public`, and `data/playerboard`.
- Added generated-backup ignore rules to `.gitignore`.
- Added `tools/ops/cleanup_generated_backups.py` with `argparse`, `--dry-run`, and explicit `--delete` mutation behavior.
- Added `Settings.current_season`, `MLB_CURRENT_SEASON`, and query-aware season fallback helpers.
- Replaced hardcoded service-default season fallbacks with centralized settings defaults.
- Added regression tests for `current_season` and generated-backup cleanup.

## Verified

- `python -m pytest` → `166 passed`
- `ruff check mlb_app tools tests` → passed
- `make verify-locks` → passed
- No root `PHASE*.md`, `STAGE*.md`, `*.patch`, `patch_*.py`, `check_*.py`, or `inspect_*.py` files remain.
- No generated backup/header-mismatch files remain under `mlb_app`, `public`, or `data/playerboard`.

## Sprint 2 handoff

The remaining production-boundary violation is intentional and tracked for Sprint 2: `mlb_app.services.playerboard_service` still imports root `playerboard.py`. Sprint 2 should extract the playerboard contract, repository, and builder into `mlb_app` and reduce root `playerboard.py` to a CLI wrapper.
