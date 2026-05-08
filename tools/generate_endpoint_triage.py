#!/usr/bin/env python3
"""Generate endpoint parity inventory for the mlb_app promotion.

This script scans the legacy app.py monolith, the canonical mlb_app route table,
and frontend/static references, then emits the Phase 1 triage CSV/Markdown files.
It is intentionally dependency-free so it can run in CI.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def section(text: str, start: str, end: str | None = None) -> str:
    s = text.index(start)
    e = text.index(end, s) if end else len(text)
    return text[s:e]


def behavior_after(sec: str, match_end: int) -> str:
    snippet = sec[match_end : match_end + 650]
    match = re.search(r"json_response\(self,\s*([^\n\r]+?)(?:,\s*(?:HTTPStatus\.)?[A-Z_0-9]+|\)|$)", snippet)
    if match:
        return re.sub(r"\s+", " ", match.group(1).strip())[:160]
    return ""


def add_route(routes: dict[tuple[str, str], dict[str, Any]], method: str, path: str, source: str, behavior: str = "", notes: str = "") -> None:
    item = routes.setdefault(
        (method, path),
        {
            "method": method,
            "endpoint": path,
            "legacy_source": source,
            "legacy_behavior": "",
            "frontend_references": "",
            "mlb_app_equivalent": "",
            "classification": "",
            "risk": "",
            "owner": "TBD",
            "status": "",
            "next_action": "",
            "notes": "",
        },
    )
    if behavior and not item["legacy_behavior"]:
        item["legacy_behavior"] = behavior
    if notes:
        item["notes"] = (item["notes"] + "; " if item["notes"] else "") + notes


def generate(root: Path, out: Path) -> dict[str, Any]:
    app_text = read(root / "app.py")
    server_text = read(root / "mlb_app" / "server.py")
    out.mkdir(parents=True, exist_ok=True)

    post_only_match = re.search(r"POST_ONLY_ENDPOINTS\s*=\s*\{(?P<body>.*?)\n\}", app_text, re.S)
    post_only = set(re.findall(r"[\"']([^\"']+)[\"']", post_only_match.group("body") if post_only_match else ""))

    handle_post = section(app_text, "    def handle_action_post", "    def do_GET")
    do_get = section(app_text, "    def do_GET", "    def do_POST")
    do_post = section(app_text, "    def do_POST", "    def serve_static")

    mlb_routes: dict[tuple[str, str], str] = {}
    for match in re.finditer(r"router\.add\([\"'](?P<method>GET|POST|PUT|PATCH|DELETE)[\"'],\s*[\"'](?P<path>[^\"']+)[\"'],\s*(?P<handler>[A-Za-z_][A-Za-z0-9_]*)", server_text):
        mlb_routes[(match.group("method"), match.group("path"))] = match.group("handler")

    refs: dict[str, set[str]] = defaultdict(set)
    for base in ["public", ".github", "docs"]:
        if not (root / base).exists():
            continue
        for path in (root / base).rglob("*"):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for endpoint in sorted(set(re.findall(r"/api/[A-Za-z0-9_./-]+", content))):
                refs[endpoint].add(str(path.relative_to(root)))

    routes: dict[tuple[str, str], dict[str, Any]] = {}
    for match in re.finditer(r"if\s+parsed\.path\s*==\s*[\"']([^\"']+)[\"']", handle_post):
        add_route(routes, "POST", match.group(1), "app.py:handle_action_post", behavior_after(handle_post, match.end()), "Legacy action-header gated mutation")
    for match in re.finditer(r"if\s+parsed\.path\s*==\s*[\"']([^\"']+)[\"']", do_get):
        path = match.group(1)
        if path not in post_only:
            add_route(routes, "GET", path, "app.py:do_GET", behavior_after(do_get, match.end()))
    for match in re.finditer(r"if\s+parsed\.path\.startswith\([\"']([^\"']+)[\"']\)", do_get):
        add_route(routes, "GET", match.group(1) + "{param}", "app.py:do_GET", behavior_after(do_get, match.end()), "Dynamic prefix route")
    for match in re.finditer(r"if\s+parsed\.path\s*==\s*[\"']([^\"']+)[\"']", do_post):
        add_route(routes, "POST", match.group(1), "app.py:do_POST", behavior_after(do_post, match.end()))
    for endpoint in ["/api/upload", "/api/import-url"]:
        add_route(routes, "POST", endpoint, "app.py:do_POST", "process_dataset_payload(csv_type, raw, filename, dataset_url)", "Legacy file/import mutation path")
    for endpoint in sorted(post_only):
        add_route(routes, "POST", endpoint, "app.py:POST_ONLY_ENDPOINTS", notes="POST-only endpoint set")

    admin_keywords = ["/sync", "/catchup", "/backfill", "/build", "/cross-reference", "/train", "/prepare", "/pipeline/", "/daily-workflow/", "/weather/", "/savant/", "/umpire/", "/platoon-splits/", "/season-cache/", "/incremental-features/", "/model-data/refresh", "/refresh-sources", "/upload", "/import-url"]
    replace_keywords = ["/predictions/grade", "/predictions/save", "/predictions/dashboard", "/predictions/status", "/model-data/", "/prop-ml/predict", "/moneyline/predict", "/ml/predict", "/predict", "/predict-pitcher", "/unified-prop-card/predict", "/all-data-prop/predict", "/all-data-prop/save-prediction", "/all-data-prop/build-bvp", "/prop-board/analyze"]
    retire_keywords = ["/github", "/mlb/command", "/ocr/parse", "/docs/"]
    core_prefixes = ["/api/app/status", "/api/edge-board", "/api/prop-detail", "/api/playerboard", "/api/playerboard/health", "/api/model-cards", "/api/model-card", "/api/data-health", "/api/data-health/dashboard", "/api/grading/health", "/api/workflows/health", "/api/prop-ml/status", "/api/my-picks", "/api/bankroll/settings", "/api/exposure/summary", "/api/game-context", "/api/game/lineup", "/api/player/", "/api/player-recent", "/api/players", "/api/saved-", "/api/team-props", "/api/odds-market-signals", "/api/insights/feed", "/api/stage3/"]
    external_refs = ["/api/espn/", "/api/mlb/", "/api/propline/props"]

    def has_any(path: str, needles: list[str]) -> bool:
        return any(needle in path for needle in needles)

    def starts_any(path: str, prefixes: list[str]) -> bool:
        return any(path.startswith(prefix) for prefix in prefixes)

    for key, item in routes.items():
        method, endpoint = key
        handler = mlb_routes.get(key)
        if handler:
            item["mlb_app_equivalent"] = f"{method} {endpoint} -> {handler}"
            item["classification"] = "PORT"
            item["status"] = "PORTED_IN_MLB_APP"
            item["risk"] = "LOW" if method == "GET" else "MEDIUM"
            item["next_action"] = "Contract-test against app.py, then retire legacy branch after parity sign-off."
        elif has_any(endpoint, retire_keywords):
            item["mlb_app_equivalent"] = "None planned"
            item["classification"] = "RETIRE"
            item["status"] = "NEEDS_USAGE_CONFIRMATION"
            item["risk"] = "LOW"
            item["next_action"] = "Confirm no primary Outlier UI or CI dependency; remove from production path."
        elif has_any(endpoint, admin_keywords):
            item["mlb_app_equivalent"] = "Admin boundary / CLI / scheduled workflow TBD"
            item["classification"] = "QUARANTINE"
            item["status"] = "NOT_PORTED"
            item["risk"] = "HIGH"
            item["next_action"] = "Move behind auth/rate-limit/request-id boundary or replace with operator CLI/job."
        elif has_any(endpoint, replace_keywords):
            item["mlb_app_equivalent"] = "Service redesign TBD"
            item["classification"] = "REPLACE"
            item["status"] = "NOT_PORTED"
            item["risk"] = "HIGH" if method == "POST" else "MEDIUM"
            item["next_action"] = "Define schema and service contract before exposing through mlb_app."
        elif starts_any(endpoint, external_refs):
            item["mlb_app_equivalent"] = "Repository/service wrapper TBD"
            item["classification"] = "REPLACE"
            item["status"] = "NOT_PORTED"
            item["risk"] = "MEDIUM"
            item["next_action"] = "Wrap external API access with timeout, token handling, and explicit data-health state."
        elif starts_any(endpoint, core_prefixes) or refs.get(endpoint):
            item["mlb_app_equivalent"] = "Thin route -> service -> repository TBD"
            item["classification"] = "PORT"
            item["status"] = "NOT_PORTED"
            item["risk"] = "MEDIUM" if method == "POST" else "LOW"
            item["next_action"] = "Port only if still used by Outlier UI; preserve API response shape."
        else:
            item["mlb_app_equivalent"] = "TBD"
            item["classification"] = "PORT"
            item["status"] = "NEEDS_OWNER_REVIEW"
            item["risk"] = "MEDIUM"
            item["next_action"] = "Assign owner and decide whether current UI/product still requires it."

        exact_refs = refs.get(endpoint, set())
        if endpoint.endswith("{param}"):
            prefix = endpoint.removesuffix("{param}")
            exact_refs |= {filename for ref, files in refs.items() if ref.startswith(prefix) for filename in files}
        item["frontend_references"] = "; ".join(sorted(exact_refs))
        if method != "GET" or any(token in endpoint for token in ["/sync", "/refresh", "/train", "/grade", "/save", "/build", "/backfill", "/upload", "/import-url", "/catchup"]):
            item["notes"] = (item["notes"] + "; " if item["notes"] else "") + "Mutation/workflow-sensitive"

    fieldnames = ["endpoint", "method", "legacy_behavior", "mlb_app_equivalent", "classification", "risk", "owner", "status", "next_action", "frontend_references", "legacy_source", "notes"]
    rows = [routes[key] for key in sorted(routes)]
    with (out / "endpoint_triage_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    counts: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["classification"]] += 1
        status_counts[row["status"]] += 1
    summary = {
        "total_endpoint_rows": len(rows),
        "unique_paths": len({row["endpoint"] for row in rows}),
        "classification_counts": dict(sorted(counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "mlb_app_registered_routes": len(mlb_routes),
        "legacy_post_only_endpoints": len(post_only),
    }
    (out / "endpoint_triage_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=Path("docs/endpoint-triage"))
    args = parser.parse_args()
    summary = generate(args.root.resolve(), args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
