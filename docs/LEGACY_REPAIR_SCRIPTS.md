# Legacy Repair Scripts

The repository contains many historical `patch_*`, `inspect_*`, and `check_*` scripts. They should be treated as legacy repair utilities, not product entry points.

## Policy

- Do not call legacy repair scripts from bettor-facing routes.
- Prefer moving durable behavior into `mlb_app/services/` with tests.
- Keep ad-hoc scripts out of the safe export unless they are source-controlled and documented.
- Retire scripts once their behavior is covered by a service, workflow, or contract test.

## Candidate families to retire over time

- `patch_*`
- `inspect_*`
- one-off `check_*` scripts
- probe scripts for external APIs

Before deleting a script, confirm no workflow or documented local process still references it.
