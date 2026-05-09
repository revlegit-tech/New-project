#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ALLOWED_TRACKED_FILES = {".env.example", ".env.template"}

FORBIDDEN_TRACKED_PATTERNS = (
    ".env",
    ".env.*",
    "*.env",
    ".en",
    "*.key",
    "*.pem",
    "secrets.*",
)

PRODUCTION_ENV_NAMES = ("MLB_ENV", "APP_ENV", "ENVIRONMENT", "ENV", "RAILWAY_ENVIRONMENT", "VERCEL_ENV", "NODE_ENV")
PRODUCTION_HOSTNAME_NAMES = (
    "MLB_PUBLIC_HOSTNAME",
    "PUBLIC_HOSTNAME",
    "RENDER_EXTERNAL_HOSTNAME",
    "RAILWAY_PUBLIC_DOMAIN",
    "FLY_APP_NAME",
    "HEROKU_APP_NAME",
)
LOCAL_HOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", ".local")
TRUE_VALUES = {"1", "true", "yes", "on"}
STRICT_VALUES = TRUE_VALUES | {"strict", "error", "fail"}


def _norm(value: object) -> str:
    return str(value or "").strip()


def _is_truthy(value: object) -> bool:
    return _norm(value).lower() in TRUE_VALUES


def matches(path: str) -> bool:
    name = Path(path).name
    if path in ALLOWED_TRACKED_FILES or name in ALLOWED_TRACKED_FILES:
        return False
    return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in FORBIDDEN_TRACKED_PATTERNS)


def tracked_files() -> list[str]:
    try:
        completed = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def production_indicators(env: Mapping[str, str] | None = None) -> list[str]:
    """Return concrete reasons the current process looks production-like.

    The guard intentionally avoids treating a generic OS HOSTNAME as production;
    container runtimes set it even for local development. Only explicit app/env
    variables, public hosting hostnames, or TLS port 443 are considered signals.
    """

    source = env or os.environ
    reasons: list[str] = []

    port = _norm(source.get("PORT"))
    if port == "443":
        reasons.append("PORT=443")

    for name in PRODUCTION_ENV_NAMES:
        value = _norm(source.get(name))
        if value.lower() in {"prod", "production"}:
            reasons.append(f"{name}={value}")

    for name in PRODUCTION_HOSTNAME_NAMES:
        value = _norm(source.get(name))
        if not value:
            continue
        lower = value.lower()
        if any(marker in lower for marker in LOCAL_HOST_MARKERS):
            continue
        reasons.append(f"{name}={value}")

    return reasons


def csp_report_only_warnings(env: Mapping[str, str] | None = None) -> list[str]:
    source = env or os.environ
    if not _is_truthy(source.get("MLB_CSP_REPORT_ONLY")):
        return []
    indicators = production_indicators(source)
    if not indicators:
        return []
    return [
        "MLB_CSP_REPORT_ONLY=1 while apparent production was detected "
        f"({', '.join(indicators)}). Production should enforce CSP; set "
        "MLB_CSP_REPORT_ONLY=0 unless you are in a temporary UI migration or emergency debugging window."
    ]


def _strict_mode(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> bool:
    if bool(args.strict):
        return True
    return _norm((env or os.environ).get("MLB_SECURITY_PREFLIGHT_STRICT")).lower() in STRICT_VALUES


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repository security preflight checks.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Promote production security posture warnings to a non-zero exit code.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = parse_args(argv)
    source = env or os.environ

    offenders = [path for path in tracked_files() if matches(path)]
    if offenders:
        print("Forbidden secret-bearing files are tracked:", file=sys.stderr)
        for path in offenders:
            print(f"  - {path}", file=sys.stderr)
        print("Run: git rm --cached <file> and rotate any exposed secret values.", file=sys.stderr)
        return 2

    warnings = csp_report_only_warnings(source)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if warnings and _strict_mode(args, source):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
