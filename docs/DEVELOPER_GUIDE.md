# Developer Guide

This project has completed production promotion into a service-oriented MLB betting research platform. `mlb_app/` is the canonical runtime; the legacy root entrypoint has been retired from the production tree.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
```

For UI smoke tests:

```bash
npm install
npm run install:browsers
```

## Daily commands

```bash
make test              # Python tests
make coverage          # Coverage report for modular source/tools
make lint              # Ruff over mlb_app, tools, and tests
make typecheck         # Mypy over mlb_app
make ci                # Security + lint + typecheck + tests
make run               # Canonical local mlb_app server
make serve             # Production-style Gunicorn/WSGI runtime
make serve-asgi        # Experimental ASGI comparison runtime
make run-modular       # Compatibility alias for make run
make safe-export       # Source-only safe zip
```

## Architecture migration rule

For new endpoint work:

1. Add a route in `mlb_app/routes/`.
2. Keep business logic in `mlb_app/services/`.
3. Put file access in `mlb_app/repositories/`.
4. Define stable dataclass contracts in `mlb_app/schemas/`.
5. Add or update API contract tests before wiring the endpoint into the modular router.
6. Keep public API response contracts stable unless a versioned contract change is explicitly tested.

## Quality gates

A pull request should pass:

```bash
make security
make lint
make typecheck
make test
make test-contracts
make validate-retirement
```

For bettor-facing UI changes, also run:

```bash
make test-ui
```

## Generated data policy

Generated CSVs, cache files, model artifacts, health reports, screenshots, and logs should not be committed as normal source. GitHub workflows now upload generated outputs as artifacts instead of pushing directly to `main`.

Use `tools/export_project.py` for sharing source code. It excludes secrets and generated data by default.
