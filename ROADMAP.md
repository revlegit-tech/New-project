# Production Roadmap Snapshot

The stabilization release follows the uploaded 9-phase roadmap. The current execution focus is Sprint 1: Foundation Cleanup.

## Sprint 1 exit criteria

- Clean install works from deterministic lockfiles.
- Tests pass.
- Root directory is understandable.
- Generated backup files do not appear in Git status.
- `mlb_app` is documented as the production boundary.
- `Settings.current_season` is the central source of the active MLB season.

## Next sprint

Sprint 2 extracts playerboard contracts and removes runtime imports from root `playerboard.py` into `mlb_app`.
