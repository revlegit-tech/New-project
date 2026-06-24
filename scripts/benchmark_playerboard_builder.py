from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.playerboard_builder import build_playerboard


WARNING_THRESHOLD_SECONDS = 90.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Playerboard builder throughput.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--source-mode", default="propline")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.environ["PLAYERBOARD_BUILD_WORKERS"] = str(max(1, int(args.workers or 1)))
    started = time.perf_counter()
    payload = build_playerboard(
        season=args.season,
        date_label=args.date,
        limit=args.limit,
        save=not args.no_save,
        source_mode=args.source_mode,
    )
    elapsed = time.perf_counter() - started
    summary = {
        "elapsedSeconds": round(elapsed, 3),
        "propsLoaded": payload.get("propsLoaded", 0),
        "cardsBuilt": payload.get("cardsBuilt", 0),
        "unsupportedSkipped": payload.get("skipped", {}).get("unsupportedMarkets", {}),
        "propsPerSecond": payload.get("performance", {}).get("propsPerSecond", 0),
        "cardsPerSecond": payload.get("performance", {}).get("cardsPerSecond", 0),
        "timings": payload.get("timings", {}),
        "cacheCounters": {
            "cacheHits": payload.get("cacheHits", 0),
            "cacheMisses": payload.get("cacheMisses", 0),
            "hitProfileCacheHits": payload.get("hitProfileCacheHits", 0),
            "hitProfileCacheMisses": payload.get("hitProfileCacheMisses", 0),
            "historyCacheHits": payload.get("historyCacheHits", 0),
            "historyCacheMisses": payload.get("historyCacheMisses", 0),
            "contextCacheHits": payload.get("contextCacheHits", 0),
            "contextCacheMisses": payload.get("contextCacheMisses", 0),
        },
    }
    warning = benchmark_warning(summary, threshold_seconds=WARNING_THRESHOLD_SECONDS)
    if warning:
        summary["warning"] = warning
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def benchmark_warning(summary: dict, *, threshold_seconds: float = WARNING_THRESHOLD_SECONDS) -> str:
    elapsed = float(summary.get("elapsedSeconds") or 0)
    if elapsed <= threshold_seconds:
        return ""
    timings = summary.get("timings") if isinstance(summary.get("timings"), dict) else {}
    slowest_name = ""
    slowest_value = -1.0
    for key, value in timings.items():
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > slowest_value and key != "totalMs":
            slowest_name = str(key)
            slowest_value = parsed
    return f"Benchmark exceeded {threshold_seconds:g}s; slowest timing bucket is {slowest_name or 'unknown'}."


if __name__ == "__main__":
    raise SystemExit(main())
