FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/ ./requirements/
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements/ml.lock.txt

COPY mlb_app/ ./mlb_app/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY daily_ml_workflow.py ./
COPY public/ ./public/

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"

CMD ["gunicorn", "--config", "config/gunicorn.asgi.conf.py", "-k", "uvicorn.workers.UvicornWorker", "mlb_app.asgi:app"]
