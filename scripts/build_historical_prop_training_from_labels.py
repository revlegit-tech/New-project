from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.services.ml_feature_schema import blocked_feature_names

DEFAULT_LABELS_DIR = Path("data/warehouse/ml_labels")
DEFAULT_FEATURES_DIR = Path("data/warehouse/ml_features")
DEFAULT_TRAINING_DIR = Path("data/warehouse/ml_training")
DEFAULT_PLAYERBOARD = Path("data/playerboard/playerboard_2026.csv")
DEFAULT_OUT = Path("data/training/historical_props_from_ml_labels_joined.csv")
DEFAULT_SUMMARY_OUT = Path("data/training/historical_props_from_ml_labels_joined_summary.json")

IDENTITY_COLUMNS = {
    "date",
    "season",
    "player",
    "team",
    "opponent",
    "market",
    "side",
    "line",
    "book",
    "american_odds",
    "prop_key",
    "source_row_id",
    "training_join_key",
    "source",
}
OUTPUT_BASE_COLUMNS = [
    "date",
    "player",
    "market",
    "line",
    "american_odds",
    "actual",
    "over",
    "result",
    "team",
    "opponent",
    "book",
    "side",
    "source",
    "source_row_id",
    "prop_key",
    "training_join_key",
    "feature_source_file",
]
LABEL_LEAKAGE_COLUMNS = {
    "actual",
    "actual_value",
    "actualvalue",
    "actual_stat",
    "actualstat",
    "result",
    "hit",
    "miss",
    "push",
    "void",
    "grade",
    "profit_1u",
    "profit1u",
    "graded_at",
    "gradedat",
    "label_status",
    "label_reason",
    "target",
    "over",
    "won",
}
BLOCKED_COLUMNS = {name.lower() for name in blocked_feature_names()} | LABEL_LEAKAGE_COLUMNS


@dataclass(frozen=True)
class FeatureMatch:
    row: dict[str, Any]
    method: str
    source_file: str


def clean(value: Any) -> str:
    return str(value or "").strip()


def to_float(value: Any) -> float | None:
    text = clean(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def truthy(value: Any) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y", "win", "won", "hit"}


def normalized_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", clean(value).lower()).strip()


def normalized_line(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return normalized_text(value)
    return f"{number:g}"


def normalize_side(value: Any) -> str:
    text = normalized_text(value)
    if text in {"o", "over"}:
        return "over"
    if text in {"u", "under"}:
        return "under"
    return text


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def file_date(path: Path) -> date | None:
    match = re.search(r"player_prop_labels_(\d{4}-\d{2}-\d{2})\.csv$", path.name)
    if not match:
        return None
    try:
        return parse_date(match.group(1))
    except ValueError:
        return None


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def selected_label_files(labels_dir: Path, start_date: str | None, end_date: str | None) -> list[Path]:
    start = parse_date(start_date) if start_date else None
    end = parse_date(end_date) if end_date else None
    files: list[Path] = []
    for path in sorted(labels_dir.glob("player_prop_labels_*.csv")):
        current = file_date(path)
        if current is None:
            continue
        if start and current < start:
            continue
        if end and current > end:
            continue
        files.append(path)
    return files


def label_date(row: Mapping[str, Any], fallback: Path) -> str:
    return clean(row.get("date")) or (file_date(fallback).isoformat() if file_date(fallback) else "")


def is_push_or_void(row: Mapping[str, Any]) -> tuple[bool, str]:
    result = normalized_text(row.get("result"))
    if truthy(row.get("push")) or result == "push":
        return True, "push"
    if truthy(row.get("void")) or result == "void":
        return True, "void"
    return False, ""


def converted_outcome(row: Mapping[str, Any]) -> tuple[int | None, str, str]:
    actual = to_float(row.get("actual_value") or row.get("actual"))
    line = to_float(row.get("line"))
    if actual is not None and line is not None:
        if actual == line:
            return None, "", "push"
        over = 1 if actual > line else 0
        return over, "win" if over else "loss", ""

    text = normalized_text(row.get("result"))
    hit = normalized_text(row.get("hit"))
    if text in {"hit", "win", "won", "over"} or hit in {"1", "true", "yes", "y"}:
        return 1, "win", ""
    if text in {"miss", "loss", "lost", "under"} or hit in {"0", "false", "no", "n"}:
        return 0, "loss", ""
    return None, "", "missing_outcome"


def safe_column_name(name: str) -> bool:
    lower = name.lower()
    if lower.startswith("target_"):
        return False
    if lower in BLOCKED_COLUMNS:
        return False
    return True


def alias_columns(row: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "propKey": "prop_key",
        "id": "source_row_id",
        "rawLabel": "side",
        "americanOdds": "american_odds",
        "impliedProbabilityPercent": "implied_probability_percent",
        "modelProbabilityPercent": "model_probability_percent",
        "finalProbabilityPercent": "model_probability_percent",
        "sportsbookImpliedPercent": "implied_probability_percent",
        "bookKey": "book_key",
        "snapshotAt": "snapshot_at",
    }
    out = dict(row)
    for source, target in aliases.items():
        if source in out and target not in out:
            out[target] = out[source]
    if "book" not in out and "bookKey" in out:
        out["book"] = out.get("bookKey")
    return out


def normalize_feature_row(row: Mapping[str, Any], *, source_file: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in row.items():
        key = clean(raw_key)
        if not key:
            continue
        lower = key.lower()
        if lower.startswith("feature_"):
            key = key[len("feature_") :]
            lower = key.lower()
        elif lower.startswith("meta_"):
            key = key[len("meta_") :]
            if key == "game_date":
                key = "date"
            lower = key.lower()
        if not safe_column_name(key):
            continue
        out[key] = value
    out = alias_columns(out)
    if "training_join_key" not in out and "training_join_key" in row:
        out["training_join_key"] = row.get("training_join_key")
    if "source_file" not in out:
        out["feature_source_file"] = str(source_file)
    return out


def load_feature_sources(
    *,
    date_label: str,
    features_dir: Path,
    training_dir: Path,
    playerboard: Path,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    sources = [
        features_dir / f"player_prop_features_{date_label}.csv",
        training_dir / f"player_prop_training_{date_label}.csv",
        playerboard,
    ]
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen: set[tuple[str, int]] = set()
    for path in sources:
        raw_rows = read_csv(path)
        if not raw_rows:
            continue
        if path == playerboard:
            raw_rows = [row for row in raw_rows if clean(row.get("date")) == date_label]
        for index, raw in enumerate(raw_rows):
            marker = (str(path), index)
            if marker in seen:
                continue
            seen.add(marker)
            normalized = normalize_feature_row(raw, source_file=path)
            normalized["_source_priority"] = sources.index(path)
            normalized["_feature_source_file"] = str(path)
            rows.append(normalized)
            counts[str(path)] += 1
    return rows, counts


def primary_keys(row: Mapping[str, Any]) -> list[str]:
    keys = []
    for field in ("prop_key", "source_row_id", "training_join_key"):
        value = clean(row.get(field))
        if value:
            keys.append(f"{field}:{value}")
    return keys


def full_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        clean(row.get("date")),
        normalized_text(row.get("market")),
        normalized_name(row.get("player")),
        normalized_text(row.get("team")),
        normalized_text(row.get("opponent")),
        normalized_line(row.get("line")),
        normalize_side(row.get("side")),
    )


def simple_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        clean(row.get("date")),
        normalized_text(row.get("market")),
        normalized_name(row.get("player")),
        normalized_line(row.get("line")),
    )


def first_by_source_priority(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: int(row.get("_source_priority", 99)))[0]


def build_indexes(feature_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    primary: dict[str, list[dict[str, Any]]] = defaultdict(list)
    full: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    simple: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in feature_rows:
        for key in primary_keys(row):
            primary[key].append(row)
        full[full_key(row)].append(row)
        simple[simple_key(row)].append(row)
    return {"primary": primary, "full": full, "simple": simple}


def unambiguous(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    source_priorities = sorted({int(row.get("_source_priority", 99)) for row in rows})
    preferred = [row for row in rows if int(row.get("_source_priority", 99)) == source_priorities[0]]
    signatures = {
        (
            clean(row.get("prop_key")),
            clean(row.get("source_row_id")),
            full_key(row),
        )
        for row in preferred
    }
    if len(signatures) == 1:
        return preferred[0]
    return None


def match_feature(label: Mapping[str, Any], indexes: Mapping[str, Any]) -> FeatureMatch | None:
    for key in primary_keys(label):
        match = first_by_source_priority(indexes["primary"].get(key, []))
        if match:
            return FeatureMatch(match, key.split(":", 1)[0], clean(match.get("_feature_source_file")))

    match = first_by_source_priority(indexes["full"].get(full_key(label), []))
    if match:
        return FeatureMatch(match, "date_market_player_team_opponent_line_side", clean(match.get("_feature_source_file")))

    simple_matches = indexes["simple"].get(simple_key(label), [])
    match = unambiguous(simple_matches)
    if match:
        return FeatureMatch(match, "date_market_player_line_unambiguous", clean(match.get("_feature_source_file")))
    return None


def feature_payload(feature: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in feature.items():
        text = clean(key)
        lower = text.lower()
        if not text or text.startswith("_"):
            continue
        if lower in BLOCKED_COLUMNS or lower.startswith("target_"):
            continue
        if lower in {"feature_source_file"}:
            continue
        payload[text] = value
    return payload


def output_row(label: Mapping[str, Any], feature: Mapping[str, Any], outcome_over: int, result: str, match: FeatureMatch) -> dict[str, Any]:
    features = feature_payload(feature)
    row = dict(features)
    row.update(
        {
            "date": clean(label.get("date")) or clean(feature.get("date")),
            "player": clean(label.get("player")) or clean(feature.get("player")),
            "market": clean(label.get("market")) or clean(feature.get("market")),
            "line": clean(label.get("line")) or clean(feature.get("line")),
            "american_odds": clean(feature.get("american_odds")) or clean(label.get("american_odds")),
            "actual": clean(label.get("actual_value") or label.get("actual")),
            "over": str(outcome_over),
            "result": result,
            "team": clean(label.get("team")) or clean(feature.get("team")),
            "opponent": clean(label.get("opponent")) or clean(feature.get("opponent")),
            "book": clean(feature.get("book")) or clean(label.get("book")),
            "side": clean(label.get("side")) or clean(feature.get("side")),
            "source": clean(feature.get("source")) or clean(label.get("source_file")),
            "source_row_id": clean(label.get("source_row_id")) or clean(feature.get("source_row_id")),
            "prop_key": clean(label.get("prop_key")) or clean(feature.get("prop_key")),
            "training_join_key": clean(feature.get("training_join_key")) or clean(label.get("training_join_key")) or clean(label.get("prop_key")),
            "feature_source_file": match.source_file,
            "join_method": match.method,
        }
    )
    return {key: value for key, value in row.items() if safe_column_name(key) or key in {"actual", "over", "result"}}


def output_columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    columns = list(OUTPUT_BASE_COLUMNS) + ["join_method"]
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def build_historical_training(
    *,
    season: int,
    start_date: str | None,
    end_date: str | None,
    labels_dir: Path,
    features_dir: Path,
    training_dir: Path,
    playerboard: Path,
    out: Path,
    summary_out: Path,
    dry_run: bool,
) -> dict[str, Any]:
    label_files = selected_label_files(labels_dir, start_date, end_date)
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    source_file_counts: Counter[str] = Counter()
    feature_source_file_counts: Counter[str] = Counter()
    loaded = 0
    used_labels = 0

    feature_cache: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    for label_file in label_files:
        label_rows = read_csv(label_file)
        source_file_counts[str(label_file)] += len(label_rows)
        loaded += len(label_rows)
        for raw_label in label_rows:
            if clean(raw_label.get("season")) and clean(raw_label.get("season")) != str(season):
                skipped["wrong_season"] += 1
                continue
            if normalized_text(raw_label.get("label_status")) != "graded":
                skipped["not_graded"] += 1
                continue
            push_or_void, reason = is_push_or_void(raw_label)
            if push_or_void:
                skipped[reason] += 1
                continue
            outcome_over, result, reason = converted_outcome(raw_label)
            if reason == "push":
                skipped["push"] += 1
                continue
            if outcome_over is None:
                skipped[reason or "missing_outcome"] += 1
                continue

            date_label = label_date(raw_label, label_file)
            if not date_label:
                skipped["missing_date"] += 1
                continue
            label = dict(raw_label)
            label["date"] = date_label

            if date_label not in feature_cache:
                feature_rows, feature_counts = load_feature_sources(
                    date_label=date_label,
                    features_dir=features_dir,
                    training_dir=training_dir,
                    playerboard=playerboard,
                )
                feature_source_file_counts.update(feature_counts)
                feature_cache[date_label] = (feature_rows, build_indexes(feature_rows))

            _, indexes = feature_cache[date_label]
            match = match_feature(label, indexes)
            if not match:
                skipped["no_feature_match"] += 1
                continue
            rows.append(output_row(label, match.row, outcome_over, result, match))
            used_labels += 1

    rows_by_date = Counter(clean(row.get("date")) or "unknown" for row in rows)
    rows_by_market = Counter(clean(row.get("market")) or "unknown" for row in rows)
    class_counts_by_market: dict[str, dict[str, int]] = {}
    for market in sorted(rows_by_market):
        class_counts_by_market[market] = dict(Counter(clean(row.get("over")) for row in rows if clean(row.get("market")) == market))

    summary = {
        "season": season,
        "start_date": start_date,
        "end_date": end_date,
        "dry_run": dry_run,
        "total_labels_loaded": loaded,
        "labels_used": used_labels,
        "labels_skipped_by_reason": dict(sorted(skipped.items())),
        "rows_written": 0 if dry_run else len(rows),
        "candidate_rows": len(rows),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "rows_by_market": dict(sorted(rows_by_market.items())),
        "class_counts_by_market": class_counts_by_market,
        "source_file_counts": dict(sorted(source_file_counts.items())),
        "feature_source_file_counts": dict(sorted(feature_source_file_counts.items())),
        "out": str(out),
        "summary_out": str(summary_out),
    }

    if not dry_run:
        write_csv(out, rows, output_columns(rows))
        summary["rows_written"] = len(rows)
        write_json(summary_out, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build historical supervised MLB player prop training rows from verified labels.")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--labels-dir", default=str(DEFAULT_LABELS_DIR))
    parser.add_argument("--features-dir", default=str(DEFAULT_FEATURES_DIR))
    parser.add_argument("--training-dir", default=str(DEFAULT_TRAINING_DIR))
    parser.add_argument("--playerboard", default=str(DEFAULT_PLAYERBOARD))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--summary-out", default=str(DEFAULT_SUMMARY_OUT))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_historical_training(
        season=args.season,
        start_date=args.start_date or None,
        end_date=args.end_date or None,
        labels_dir=resolve_path(args.labels_dir),
        features_dir=resolve_path(args.features_dir),
        training_dir=resolve_path(args.training_dir),
        playerboard=resolve_path(args.playerboard),
        out=resolve_path(args.out),
        summary_out=resolve_path(args.summary_out),
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
