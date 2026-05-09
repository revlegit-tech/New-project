from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_CONFIGURED = False


def utc_ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        try:
            payload = json.loads(message)
            if not isinstance(payload, dict):
                payload = {"message": message}
        except json.JSONDecodeError:
            payload = {"message": message}
        payload.setdefault("ts", utc_ts())
        payload.setdefault("level", record.levelname)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_json_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    formatter = JsonEventFormatter()
    for name in ("mlb_app", "mlb_app.access", "mlb_app.model", "mlb_app.alerts"):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        stream_handlers = [handler for handler in logger.handlers if isinstance(handler, logging.StreamHandler)]
        if stream_handlers:
            for handler in stream_handlers:
                handler.setFormatter(formatter)
                handler.stream = sys.stdout
        else:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            logger.addHandler(handler)
    _CONFIGURED = True


def log_json(logger_name: str, level: int, event: str, **fields: Any) -> None:
    configure_json_logging()
    logging.getLogger(logger_name).log(level, json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))
