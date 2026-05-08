#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

CORE_ENDPOINTS = (
    "/api/app/status",
    "/api/edge-board",
    "/api/playerboard/health",
    "/api/model-cards",
    "/api/data-health/dashboard",
)


def check(base_url: str, endpoint: str) -> tuple[int, str]:
    url = base_url.rstrip("/") + endpoint
    with urllib.request.urlopen(url, timeout=10) as response:
        request_id = response.headers.get("X-Request-Id")
        if not request_id:
            raise RuntimeError(f"{endpoint} did not include X-Request-Id")
        body = response.read().decode("utf-8", errors="replace")
        if not body.strip().startswith("{"):
            raise RuntimeError(f"{endpoint} did not return a JSON object")
        json.loads(body)
        return response.status, f"{endpoint} requestId={request_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test the canonical mlb_app runtime")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    failures: list[str] = []
    for endpoint in CORE_ENDPOINTS:
        try:
            status, path = check(args.base_url, endpoint)
            print(f"{status} {path}")
        except (OSError, urllib.error.URLError, RuntimeError, json.JSONDecodeError) as error:
            failures.append(f"{endpoint}: {error}")
    if failures:
        print("mlb_app smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
