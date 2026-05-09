# Phase 10 — Legacy app.py Retirement

This cumulative bundle retires the root `app.py` entrypoint from the production tree.

## What changed

- Removed root `app.py` from the shipped source tree.
- Removed the `make run-legacy` command.
- Updated CI compile/smoke paths so they no longer reference `app.py`.
- Updated README/developer commands to use `mlb_app` only.
- Added `tools/validate_app_py_retirement.py`.
- Added `make validate-retirement`.
- Added tests that prevent the legacy runtime from re-entering production surfaces.

## Run locally

```bash
make run
```

Open:

```text
http://127.0.0.1:8765
```

## Run production-style WSGI

```bash
make serve
```

Open:

```text
http://127.0.0.1:8765
```

## Preview isolated Outlier UI

```text
http://127.0.0.1:8765/?view=outlier
```

## Run experimental ASGI sidecar

```bash
make serve-asgi
```

Open:

```text
http://127.0.0.1:8765
```

## Validate retirement

```bash
make validate-retirement
```

## Smoke test

```bash
make smoke
```

or against a running server:

```bash
make smoke-live
```
