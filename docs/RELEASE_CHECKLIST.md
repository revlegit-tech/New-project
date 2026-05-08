# Release Checklist

Use this before sharing a build, zip, or branch.

## Security

- [ ] Exposed keys have been rotated.
- [ ] `git ls-files` shows no `.env`, `.en`, key, pem, or secret files.
- [ ] `make security` passes.
- [ ] Safe export was created with `make safe-export`.
- [ ] The exported zip contains no generated data, caches, model artifacts, logs, screenshots, or local env files.

## Backend

- [ ] `make lint` passes.
- [ ] `make typecheck` passes.
- [ ] `make test` passes.
- [ ] `make test-contracts` passes.
- [ ] New routes have service/repository boundaries.
- [ ] Errors return safe JSON.

## Data and modeling

- [ ] `make validate-contracts` passes for the target season.
- [ ] Model training used chronological validation.
- [ ] No prediction route uses a generic model fallback unless a developer flag is explicitly enabled.
- [ ] Market readiness states are visible.

## UI

- [ ] `make test-ui` passes for desktop and mobile projects.
- [ ] Research-mode labeling is present.
- [ ] Admin workflows are hidden behind Advanced Mode.
- [ ] Missing/stale data has visible text labels, not color-only signals.

## Release note

- [ ] Update `CHANGELOG.md` with security, backend, data, and UI changes.
