.PHONY: install-dev test test-contracts coverage lint format typecheck ci run serve serve-asgi run-modular health smoke smoke-asgi smoke-live safe-export security test-ui browsers validate-contracts validate-retirement clean

PORT ?= 8765
HOST ?= 127.0.0.1
GUNICORN_WORKERS ?= 4
GUNICORN_TIMEOUT ?= 30
GUNICORN_BIND ?= 0.0.0.0:$(PORT)
SAFE_EXPORT_MAX_MB ?= 25

install-dev:
	python -m pip install --upgrade pip
	python -m pip install -r requirements.txt -r requirements-dev.txt

browsers:
	npm install
	npm run install:browsers

test:
	python -m pytest

test-contracts:
	python -m pytest tests/test_api_contracts.py tests/test_data_contracts.py

coverage:
	python -m pytest --cov=mlb_app --cov=tools --cov-report=term-missing --cov-report=html

lint:
	ruff check mlb_app tools tests

format:
	ruff format mlb_app tools tests

typecheck:
	mypy mlb_app --config-file pyproject.toml

ci: security lint typecheck test smoke validate-retirement

# Canonical local runtime: mlb_app only.
run:
	python -m mlb_app.server $(PORT) --host $(HOST)

# Production-style bounded runtime: mlb_app via Gunicorn.
serve:
	gunicorn mlb_app.wsgi:application --workers $(GUNICORN_WORKERS) --bind $(GUNICORN_BIND) --timeout $(GUNICORN_TIMEOUT) --access-logfile -

# Experimental ASGI runtime. WSGI/Gunicorn remains canonical until Phase 9 parity is proven.
serve-asgi:
	uvicorn mlb_app.asgi:app --host 0.0.0.0 --port $(PORT)


# Temporary compatibility alias for existing developer muscle memory.
run-modular: run

health:
	python - <<'SMOKEPY'
import urllib.request
for path in ("/api/app/status", "/api/edge-board", "/api/playerboard/health", "/api/model-cards", "/api/data-health/dashboard"):
    url = "http://127.0.0.1:$(PORT)" + path
    with urllib.request.urlopen(url, timeout=10) as response:
        print(response.status, path)
SMOKEPY

# Fast local smoke path. The legacy app.py runtime has been retired.
smoke:
	python -m pytest tests/test_api_contracts.py tests/test_modular_router.py tests/test_wsgi_smoke.py tests/test_asgi_migration.py tests/test_static_file_guard.py tests/test_cache_store.py tests/test_security_export.py tests/test_trust_surface_static_safety.py tests/test_request_observability.py

smoke-asgi:
	python -m pytest tests/test_asgi_migration.py

# Live endpoint smoke for a separately running mlb_app server.
smoke-live:
	python tools/smoke_mlb_app.py --base-url http://127.0.0.1:$(PORT)

test-ui:
	npm run test:e2e

safe-export:
	python tools/export_project.py --output dist/mlb-app-source.zip --max-size-mb $(SAFE_EXPORT_MAX_MB)

security:
	python tools/security_preflight.py

validate-contracts:
	python tools/validate_data_contracts.py --root . --season 2026

validate-retirement:
	python tools/validate_app_py_retirement.py --root .

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	rm -rf htmlcov .coverage playwright-report test-results dist/mlb-app-source.zip
