"""Canonical Gunicorn configuration for the MLB App ASGI runtime.

Production truth:
    mlb_app.asgi:app -> create_app -> AppContainer -> services -> repositories.

Usage:
    gunicorn --config config/gunicorn.asgi.conf.py -k uvicorn.workers.UvicornWorker mlb_app.asgi:app
"""
from __future__ import annotations

import multiprocessing
import os

worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("GUNICORN_WORKERS", os.environ.get("WEB_CONCURRENCY", "0")) or max(2, min(4, multiprocessing.cpu_count())))
bind = os.environ.get("GUNICORN_BIND", f"0.0.0.0:{os.environ.get('PORT', '8765')}")
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
