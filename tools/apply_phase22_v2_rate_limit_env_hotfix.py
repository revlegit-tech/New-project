from __future__ import annotations

"""Phase 22 v2 hotfix: load local .env and handle OddsPapi rate limits gracefully.

This patch keeps OddsPapi optional. Provider HTTP errors such as 429 are archived
and reported as warnings instead of crashing the daily refresh.
"""

from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "phase22_oddspapi_clv.py"


def backup(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = path.with_suffix(path.suffix + f".phase22v2_backup_{stamp}")
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"Missing target: {TARGET}")
    text = TARGET.read_text(encoding="utf-8")
    original = text
    bkp = backup(TARGET)

    if "import urllib.error" not in text:
        text = text.replace("import urllib.parse\nimport urllib.request", "import urllib.error\nimport urllib.parse\nimport urllib.request")

    env_block = '''\n# Load local .env when available so operator scripts do not require manual Process env export.\ntry:\n    from local_env import load_local_env\nexcept Exception:  # pragma: no cover - local_env is optional outside this repo\n    load_local_env = None\n\nif load_local_env is not None:\n    try:\n        load_local_env()\n    except Exception:\n        pass\n'''
    if "# Load local .env when available so operator scripts" not in text:
        marker = "from typing import Any, Iterable\n"
        text = text.replace(marker, marker + env_block)

    old_fetch = '''def fetch_json(url: str, params: dict[str, Any], *, timeout: int = 45) -> Any:\n    query = urllib.parse.urlencode({k: v for k, v in params.items() if clean(v)})\n    full_url = f"{url}?{query}" if query else url\n    req = urllib.request.Request(full_url, headers={"Accept": "application/json", "User-Agent": "mlb-phase22/1.0"})\n    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - operator-supplied trusted API endpoint\n        body = response.read().decode("utf-8")\n    return json.loads(body) if body else {}\n'''
    new_fetch = '''def safe_url_for_log(full_url: str) -> str:\n    api_key = clean(os.environ.get("ODDSPAPI_API_KEY"))\n    return full_url.replace(api_key, "***") if api_key else full_url\n\n\ndef provider_error_payload(error: Exception, *, full_url: str) -> dict[str, Any]:\n    if isinstance(error, urllib.error.HTTPError):\n        body = error.read().decode("utf-8", errors="replace") if error.fp else ""\n        reason = "rate_limited" if error.code == 429 else "http_error"\n        return {\n            "__phase22_provider_error__": True,\n            "status": "warning",\n            "reason": reason,\n            "httpStatus": error.code,\n            "url": safe_url_for_log(full_url),\n            "bodyHead": body[:2000],\n        }\n    return {\n        "__phase22_provider_error__": True,\n        "status": "warning",\n        "reason": type(error).__name__,\n        "url": safe_url_for_log(full_url),\n        "bodyHead": str(error)[:2000],\n    }\n\n\ndef fetch_json(url: str, params: dict[str, Any], *, timeout: int = 45) -> Any:\n    query = urllib.parse.urlencode({k: v for k, v in params.items() if clean(v)})\n    full_url = f"{url}?{query}" if query else url\n    req = urllib.request.Request(full_url, headers={"Accept": "application/json", "User-Agent": "mlb-phase22/1.0"})\n    try:\n        with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - operator-supplied trusted API endpoint\n            body = response.read().decode("utf-8")\n        return json.loads(body) if body else {}\n    except Exception as error:\n        return provider_error_payload(error, full_url=full_url)\n'''
    if old_fetch in text:
        text = text.replace(old_fetch, new_fetch)
    elif "def provider_error_payload" not in text:
        raise SystemExit("Could not find fetch_json block to replace; no changes written.")

    old_result = '''    result = {\n        "status": "ok" if provider_rows else "warning",\n        "phase": "22",\n        "date": date_label,\n        "season": season,\n        "tournamentIds": tournament_ids,\n        "bookmakers": bookmakers,\n        "oddsArchive": str(odds_archive),\n        "clvArchives": clv_archives,\n        "fixtureCount": len(fixtures),\n        "matchedProviderRows": len(provider_rows),\n        "providerClvReadyRows": sum(1 for row in provider_rows if clean(row.get("provider_status")) == "provider_clv_ready"),\n        "apply": apply_result,\n        "notes": [\n'''
    new_result = '''    provider_errors = [payload for payload in odds_payload.values() if isinstance(payload, dict) and payload.get("__phase22_provider_error__")]\n    result = {\n        "status": "ok" if provider_rows else "warning",\n        "phase": "22",\n        "date": date_label,\n        "season": season,\n        "tournamentIds": tournament_ids,\n        "bookmakers": bookmakers,\n        "oddsArchive": str(odds_archive),\n        "clvArchives": clv_archives,\n        "fixtureCount": len(fixtures),\n        "matchedProviderRows": len(provider_rows),\n        "providerClvReadyRows": sum(1 for row in provider_rows if clean(row.get("provider_status")) == "provider_clv_ready"),\n        "providerErrors": provider_errors,\n        "reason": provider_errors[0].get("reason", "") if provider_errors and not provider_rows else "",\n        "apply": apply_result,\n        "notes": [\n'''
    if old_result in text:
        text = text.replace(old_result, new_result)
    elif "providerErrors" not in text:
        raise SystemExit("Could not find result block to patch; no changes written.")

    TARGET.write_text(text, encoding="utf-8")
    print({
        "status": "ok",
        "changed": text != original,
        "path": str(TARGET),
        "backup": str(bkp),
        "reason": "Phase 22 v2 loads .env locally and records OddsPapi HTTP/rate-limit errors instead of crashing.",
    })


if __name__ == "__main__":
    main()
