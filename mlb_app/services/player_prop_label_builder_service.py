from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.ml_feature_export_service import DEFAULT_SOURCE, MLFeatureExportService
from mlb_app.services.ml_feature_schema import assert_no_leakage_fields
from mlb_app.services.player_prop_label_schema import (
    LABEL_SCHEMA_VERSION,
    assert_label_not_in_features,
    label_field_names,
    normalize_result,
)
from mlb_app.services.player_prop_market_stat_mapper import (
    grade_over_under,
    is_supported_market,
    market_to_stat_key,
    normalize_side,
)

DEFAULT_LABEL_OUTPUT_RELATIVE_DIR = Path("warehouse") / "ml_labels"
LABEL_API_SCHEMA_VERSION = "ml-labels.v1"
MAX_LABEL_ROWS = 10000

LABEL_FIELD_ORDER: tuple[str, ...] = tuple(label_field_names())
STAT_ALIASES: dict[str, tuple[str, ...]] = {
    "hits": ("hits", "h"),
    "totalBases": ("totalBases", "total_bases", "tb"),
    "homeRuns": ("homeRuns", "home_runs", "hr"),
    "rbi": ("rbi", "rbis", "runsBattedIn", "runs_batted_in"),
    "runs": ("runs", "r"),
    "baseOnBalls": ("baseOnBalls", "walks", "bb"),
    "singles": ("singles", "1b"),
    "doubles": ("doubles", "2b"),
    "stolenBases": ("stolenBases", "stolen_bases", "sb"),
    "strikeOuts": ("strikeOuts", "strikeouts", "strike_outs", "so", "k"),
    "outs": ("outs", "outsRecorded", "outs_recorded"),
    "hitsAllowed": ("hitsAllowed", "hits_allowed", "hits", "h"),
    "earnedRuns": ("earnedRuns", "earned_runs", "er"),
}
PLAYER_MARKET_SUFFIXES: tuple[str, ...] = (
    "Strikeouts Thrown",
    "Hits Allowed",
    "Earned Runs",
    "Outs Recorded",
    "Pitching Outs",
)
DATE_FIELDS: tuple[str, ...] = ("date", "game_date", "gameDate", "stat_date")
PLAYER_ID_FIELDS: tuple[str, ...] = ("playerId", "player_id", "mlbId", "mlb_id", "personId", "person_id", "id")
PLAYER_NAME_FIELDS: tuple[str, ...] = ("player", "playerName", "player_name", "name", "fullName", "full_name")
PITCHER_NAME_FIELDS: tuple[str, ...] = (
    "pitcher",
    "pitcherName",
    "pitcher_name",
    "startingPitcher",
    "probablePitcher",
    *PLAYER_NAME_FIELDS,
)
TEAM_FIELDS: tuple[str, ...] = ("team", "teamAbbr", "team_abbr", "teamCode", "team_code", "team_abbreviation")
GAME_PK_FIELDS: tuple[str, ...] = ("gamePk", "game_pk", "gameId", "game_id")
TEAM_ALIASES: dict[str, str] = {
    "ARI": "ARI",
    "ARIZONA DIAMONDBACKS": "ARI",
    "ATL": "ATL",
    "ATLANTA BRAVES": "ATL",
    "BAL": "BAL",
    "BALTIMORE ORIOLES": "BAL",
    "BOS": "BOS",
    "BOSTON RED SOX": "BOS",
    "CHC": "CHC",
    "CHICAGO CUBS": "CHC",
    "CIN": "CIN",
    "CINCINNATI REDS": "CIN",
    "CLE": "CLE",
    "CLEVELAND GUARDIANS": "CLE",
    "COL": "COL",
    "COLORADO ROCKIES": "COL",
    "CWS": "CWS",
    "CHICAGO WHITE SOX": "CWS",
    "DET": "DET",
    "DETROIT TIGERS": "DET",
    "HOU": "HOU",
    "HOUSTON ASTROS": "HOU",
    "KCR": "KCR",
    "KC": "KCR",
    "KANSAS CITY ROYALS": "KCR",
    "LAA": "LAA",
    "LOS ANGELES ANGELS": "LAA",
    "LAD": "LAD",
    "LOS ANGELES DODGERS": "LAD",
    "MIA": "MIA",
    "MIAMI MARLINS": "MIA",
    "MIL": "MIL",
    "MILWAUKEE BREWERS": "MIL",
    "MIN": "MIN",
    "MINNESOTA TWINS": "MIN",
    "NYM": "NYM",
    "NEW YORK METS": "NYM",
    "NYY": "NYY",
    "NEW YORK YANKEES": "NYY",
    "ATH": "ATH",
    "OAK": "ATH",
    "OAKLAND ATHLETICS": "ATH",
    "ATHLETICS": "ATH",
    "PHI": "PHI",
    "PHILADELPHIA PHILLIES": "PHI",
    "PIT": "PIT",
    "PITTSBURGH PIRATES": "PIT",
    "SDP": "SDP",
    "SD": "SDP",
    "SAN DIEGO PADRES": "SDP",
    "SEA": "SEA",
    "SEATTLE MARINERS": "SEA",
    "SFG": "SFG",
    "SF": "SFG",
    "SAN FRANCISCO GIANTS": "SFG",
    "STL": "STL",
    "ST. LOUIS CARDINALS": "STL",
    "ST LOUIS CARDINALS": "STL",
    "TBR": "TBR",
    "TB": "TBR",
    "TAMPA BAY RAYS": "TBR",
    "TEX": "TEX",
    "TEXAS RANGERS": "TEX",
    "TOR": "TOR",
    "TORONTO BLUE JAYS": "TOR",
    "WSN": "WSN",
    "WAS": "WSN",
    "WASHINGTON NATIONALS": "WSN",
}


@dataclass(frozen=True)
class LabelBuildResult:
    rows: list[dict[str, Any]]
    feature_rows: list[dict[str, Any]]
    manifest: dict[str, Any]


class PlayerPropLabelBuilderService:
    """Build postgame player-prop labels while keeping features untouched."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        feature_export_service: MLFeatureExportService | None = None,
    ) -> None:
        self.settings = settings
        self.feature_export_service = feature_export_service or MLFeatureExportService(settings=settings)

    def build_labels(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        include_ungraded: bool = False,
        dry_run: bool = False,
        output_format: str = "both",
        output_dir: Path | str | None = None,
        graded_at: datetime | None = None,
    ) -> dict[str, Any]:
        result = self.build_label_rows(
            date_label=date_label,
            season=season,
            source=source,
            include_ungraded=include_ungraded,
            dry_run=dry_run,
            output_format=output_format,
            output_dir=output_dir,
            graded_at=graded_at,
        )
        if dry_run:
            return result.manifest
        target_dir = Path(output_dir) if output_dir is not None else self.default_output_dir()
        paths = _planned_label_paths(target_dir, str(result.manifest["date"]), output_format)
        target_dir.mkdir(parents=True, exist_ok=True)
        result.manifest["written"] = True
        if "csv" in paths:
            _write_csv(paths["csv"], LABEL_FIELD_ORDER, result.rows)
        if "json" in paths:
            _write_json(paths["json"], {"label_schema_version": LABEL_SCHEMA_VERSION, "manifest": result.manifest, "rows": result.rows})
        _write_json(paths["manifest"], result.manifest)
        return result.manifest

    def build_label_rows(
        self,
        *,
        date_label: str,
        season: int | None = None,
        source: str = DEFAULT_SOURCE,
        include_ungraded: bool = False,
        dry_run: bool = True,
        output_format: str = "both",
        output_dir: Path | str | None = None,
        graded_at: datetime | None = None,
    ) -> LabelBuildResult:
        graded_at = graded_at or datetime.now(timezone.utc)
        selected_date = _clean(date_label) or graded_at.date().isoformat()
        selected_season = int(season or self.settings.current_season)
        target_dir = Path(output_dir) if output_dir is not None else self.default_output_dir()
        feature_rows, warnings = self._load_feature_rows(date_label=selected_date, season=selected_season, source=source)
        feature_rows = feature_rows[:MAX_LABEL_ROWS]
        logs = _StatLogs.load(self.settings, selected_season)
        warnings.extend(logs.warnings)

        all_rows: list[dict[str, Any]] = []
        for feature in feature_rows:
            assert_no_leakage_fields(feature)
            assert_label_not_in_features(feature)
            all_rows.append(self._label_for_feature(feature, logs=logs, graded_at=graded_at, date_label=selected_date, season=selected_season))

        output_rows = [row for row in all_rows if include_ungraded or row["label_status"] == "graded" or row["label_status"] == "void"]
        manifest = self._manifest(
            rows=output_rows,
            all_rows=all_rows,
            feature_rows=feature_rows,
            date_label=selected_date,
            season=selected_season,
            source=_normal_source(source),
            dry_run=dry_run,
            output_format=output_format,
            output_dir=target_dir,
            warnings=warnings,
        )
        return LabelBuildResult(rows=output_rows, feature_rows=feature_rows, manifest=manifest)

    def preview(self, *, date_label: str, limit: int = 25, season: int | None = None, source: str = DEFAULT_SOURCE) -> dict[str, Any]:
        selected_date = _clean(date_label) or datetime.now(timezone.utc).date().isoformat()
        rows, warnings = read_existing_label_rows(self.settings, selected_date)
        if not rows:
            built = self.build_label_rows(
                date_label=selected_date,
                season=season,
                source=source,
                include_ungraded=True,
                dry_run=True,
            )
            rows = built.rows
            warnings.extend(built.manifest.get("warnings") or [])
        return {
            "status": "ok",
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "date": selected_date,
            "row_count": len(rows),
            "rows": rows[: max(0, min(int(limit), 250))],
            "warnings": _dedupe(warnings)[:25],
        }

    def status_payload(self) -> dict[str, Any]:
        label = latest_player_prop_label_status(self.settings)
        training = latest_player_prop_training_status(self.settings)
        warnings = list(label.get("warnings") or []) + list(training.get("warnings") or [])
        return {
            "status": "ok",
            "enabled": True,
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "latest_label_date": label.get("latest_label_date") or "",
            "latest_label_rows": int(label.get("latest_label_rows") or 0),
            "latest_training_date": training.get("latest_training_date") or "",
            "latest_training_rows": int(training.get("latest_training_rows") or 0),
            "supported_markets": supported_markets(),
            "warnings": _dedupe(warnings)[:25],
        }

    def default_output_dir(self) -> Path:
        return self.settings.data_dir / DEFAULT_LABEL_OUTPUT_RELATIVE_DIR

    def _load_feature_rows(self, *, date_label: str, season: int, source: str) -> tuple[list[dict[str, Any]], list[str]]:
        rows, warnings = read_existing_feature_rows(self.settings, date_label)
        if rows:
            return rows, warnings
        build = self.feature_export_service.build_features(date_label=date_label, season=season, source=source)
        return build.rows, list(build.manifest.get("warnings") or [])

    def _label_for_feature(
        self,
        feature: Mapping[str, Any],
        *,
        logs: "_StatLogs",
        graded_at: datetime,
        date_label: str,
        season: int,
    ) -> dict[str, Any]:
        market = _clean(feature.get("market"))
        stat_key = market_to_stat_key(market)
        base = {
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "graded_at": graded_at.isoformat(),
            "date": _clean(feature.get("date"))[:10] or date_label,
            "season": _clean(feature.get("season")) or int(season),
            "game_pk": _clean(feature.get("game_pk") or feature.get("gamePk")),
            "player_id": _clean(feature.get("player_id") or feature.get("playerId")),
            "source_row_id": _clean(feature.get("source_row_id")) or _clean(feature.get("prop_key")),
            "prop_key": _clean(feature.get("prop_key")),
            "player": _clean(feature.get("player")),
            "team": _clean(feature.get("team")).upper(),
            "opponent": _clean(feature.get("opponent")).upper(),
            "market": market,
            "side": normalize_side(_clean(feature.get("side"))),
            "line": feature.get("line"),
            "actual_value": "",
            "result": "ungraded",
            "hit": False,
            "push": False,
            "void": False,
            "label_status": "missing_market_mapping" if not market else "unsupported_market",
            "label_reason": "Missing market mapping." if not market else f"Unsupported market: {market}",
            "stat_source": "",
            "stat_key": stat_key or "",
            "source_file": _clean(feature.get("rawSource") or feature.get("source_file") or feature.get("source")),
            "label_quality_flags": "",
        }
        if not is_supported_market(market) or stat_key is None:
            return _only_label_fields(base)
        line = _line_for_market(market, feature.get("line"))
        if line is None:
            base.update({"label_status": "invalid_line", "label_reason": "Prop line is missing or invalid."})
            return _only_label_fields(base)
        match = logs.find(
            market=market,
            date_label=str(base["date"]),
            player=str(base["player"]),
            team=str(base["team"]),
            opponent=str(base["opponent"]),
            player_id=str(base["player_id"]),
        )
        if match.status != "ok":
            base.update({"label_status": match.status, "label_reason": match.reason, "stat_source": match.source})
            return _only_label_fields(base)
        actual = _stat_value(match.row, stat_key)
        if actual is None:
            base.update(
                {
                    "label_status": "missing_stat",
                    "label_reason": f"Stat key {stat_key} was not available for the matched player log.",
                    "stat_source": match.source,
                }
            )
            return _only_label_fields(base)
        graded = grade_over_under(actual, line, str(base["side"]))
        result = normalize_result(graded["result"], hit=graded["hit"], push=graded["push"], void=graded["void"])
        base.update(
            {
                "line": line,
                "actual_value": actual,
                "result": result,
                "hit": graded["hit"],
                "push": graded["push"],
                "void": graded["void"],
                "label_status": graded["label_status"],
                "label_reason": graded["label_reason"],
                "stat_source": match.source,
            }
        )
        return _only_label_fields(base)

    def _manifest(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        all_rows: Sequence[Mapping[str, Any]],
        feature_rows: Sequence[Mapping[str, Any]],
        date_label: str,
        season: int,
        source: str,
        dry_run: bool,
        output_format: str,
        output_dir: Path,
        warnings: list[str],
    ) -> dict[str, Any]:
        result_counts = Counter(_clean(row.get("result")) or "ungraded" for row in rows)
        status_counts = Counter(_clean(row.get("label_status")) or "unknown" for row in rows)
        market_counts = Counter(_clean(row.get("market")) or "unknown" for row in rows)
        supported = sum(1 for row in all_rows if is_supported_market(_clean(row.get("market"))))
        diagnostic_warnings = _label_matching_warnings(rows)
        planned = _planned_label_paths(output_dir, date_label, output_format)
        return {
            "status": "ok",
            "schemaVersion": LABEL_API_SCHEMA_VERSION,
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "date": date_label,
            "season": int(season),
            "source": source,
            "format": _normal_format(output_format),
            "dry_run": bool(dry_run),
            "row_count": len(rows),
            "feature_row_count": len(feature_rows),
            "graded_count": int(status_counts.get("graded", 0)),
            "ungraded_count": sum(1 for row in rows if _clean(row.get("result")) == "ungraded"),
            "win_count": int(result_counts.get("hit", 0) + result_counts.get("win", 0)),
            "loss_count": int(result_counts.get("miss", 0) + result_counts.get("loss", 0)),
            "push_count": int(result_counts.get("push", 0)),
            "void_count": int(result_counts.get("void", 0)),
            "market_counts": dict(sorted(market_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "supported_market_count": supported,
            "unsupported_market_count": max(0, len(all_rows) - supported),
            "output_paths": {key: _display_path(path, self.settings) for key, path in planned.items()},
            "written": False,
            "warnings": _dedupe([*warnings, *diagnostic_warnings])[:25],
        }


def read_existing_label_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], list[str]]:
    root = settings.data_dir / DEFAULT_LABEL_OUTPUT_RELATIVE_DIR
    json_path = root / f"player_prop_labels_{date_label}.json"
    csv_path = root / f"player_prop_labels_{date_label}.csv"
    warnings: list[str] = []
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], warnings
        except (OSError, json.JSONDecodeError) as error:
            warnings.append(f"Existing label JSON unreadable: {type(error).__name__}: {error}")
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)], warnings
        except OSError as error:
            warnings.append(f"Existing label CSV unreadable: {type(error).__name__}: {error}")
    return [], warnings


def read_existing_feature_rows(settings: Settings, date_label: str) -> tuple[list[dict[str, Any]], list[str]]:
    root = settings.data_dir / "warehouse" / "ml_features"
    json_path = root / f"player_prop_features_{date_label}.json"
    csv_path = root / f"player_prop_features_{date_label}.csv"
    warnings: list[str] = []
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else [], warnings
        except (OSError, json.JSONDecodeError) as error:
            warnings.append(f"Existing feature JSON unreadable: {type(error).__name__}: {error}")
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)], warnings
        except OSError as error:
            warnings.append(f"Existing feature CSV unreadable: {type(error).__name__}: {error}")
    return [], warnings


def latest_player_prop_label_status(settings: Settings = default_settings) -> dict[str, Any]:
    manifest_paths = sorted(
        (settings.data_dir / DEFAULT_LABEL_OUTPUT_RELATIVE_DIR).glob("player_prop_label_manifest_*.json"),
        key=_safe_mtime,
        reverse=True,
    )
    if not manifest_paths:
        return {
            "enabled": True,
            "latest_label_date": "",
            "latest_label_rows": 0,
            "latest_manifest_path": "",
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "graded_count": 0,
            "ungraded_count": 0,
            "fallback_mode": "no_exports",
            "warnings": ["No player prop label manifests found."],
        }
    path = manifest_paths[0]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "enabled": True,
            "latest_label_date": "",
            "latest_label_rows": 0,
            "latest_manifest_path": _display_path(path, settings),
            "label_schema_version": LABEL_SCHEMA_VERSION,
            "graded_count": 0,
            "ungraded_count": 0,
            "fallback_mode": "manifest_unreadable",
            "warnings": [f"Latest label manifest is unreadable: {type(error).__name__}: {error}"],
        }
    return {
        "enabled": True,
        "latest_label_date": _clean(manifest.get("date")),
        "latest_label_rows": int(manifest.get("row_count") or 0),
        "latest_manifest_path": _display_path(path, settings),
        "label_schema_version": _clean(manifest.get("label_schema_version")) or LABEL_SCHEMA_VERSION,
        "graded_count": int(manifest.get("graded_count") or 0),
        "ungraded_count": int(manifest.get("ungraded_count") or 0),
        "fallback_mode": "generated_artifact",
        "warnings": [str(item) for item in manifest.get("warnings", []) if str(item).strip()],
    }


def latest_player_prop_training_status(settings: Settings = default_settings) -> dict[str, Any]:
    root = settings.data_dir / "warehouse" / "ml_training"
    manifest_paths = sorted(root.glob("player_prop_training_manifest_*.json"), key=_safe_mtime, reverse=True)
    if not manifest_paths:
        return {
            "enabled": True,
            "latest_training_date": "",
            "latest_training_rows": 0,
            "latest_manifest_path": "",
            "training_schema_version": "",
            "leakage_check_passed": None,
            "fallback_mode": "no_exports",
            "warnings": ["No player prop training manifests found."],
        }
    path = manifest_paths[0]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "enabled": True,
            "latest_training_date": "",
            "latest_training_rows": 0,
            "latest_manifest_path": _display_path(path, settings),
            "training_schema_version": "",
            "leakage_check_passed": False,
            "fallback_mode": "manifest_unreadable",
            "warnings": [f"Latest training manifest is unreadable: {type(error).__name__}: {error}"],
        }
    return {
        "enabled": True,
        "latest_training_date": _clean(manifest.get("date")),
        "latest_training_rows": int(manifest.get("joined_row_count") or 0),
        "latest_manifest_path": _display_path(path, settings),
        "training_schema_version": _clean(manifest.get("training_schema_version")),
        "leakage_check_passed": bool(manifest.get("leakage_check_passed")),
        "fallback_mode": "generated_artifact",
        "warnings": [str(item) for item in manifest.get("warnings", []) if str(item).strip()],
    }


def supported_markets() -> list[str]:
    from mlb_app.services.player_prop_market_stat_mapper import MARKET_STAT_KEYS

    return sorted(MARKET_STAT_KEYS)


@dataclass(frozen=True)
class _LogMatch:
    status: str
    reason: str
    row: dict[str, str]
    source: str


@dataclass(frozen=True)
class _StatLogs:
    batter_rows: list[dict[str, str]]
    pitcher_rows: list[dict[str, str]]
    batter_source: str
    pitcher_source: str
    warnings: list[str]

    @classmethod
    def load(cls, settings: Settings, season: int) -> "_StatLogs":
        batter_rows, batter_source = _merged_existing_rows(
            [
                settings.data_dir / "warehouse" / "season_logs" / f"batter_game_logs_{season}.csv",
                settings.data_dir / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv",
                settings.data_dir / "cache" / "incremental_stats" / f"batter_game_logs_{season}.csv",
            ]
        )
        pitcher_rows, pitcher_source = _merged_existing_rows(
            [
                settings.data_dir / "warehouse" / "season_logs" / f"pitcher_game_logs_{season}.csv",
                settings.data_dir / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv",
                settings.data_dir / "cache" / "incremental_stats" / f"pitcher_game_logs_{season}.csv",
            ]
        )
        warnings: list[str] = []
        if not batter_rows:
            warnings.append(f"No batter season logs found for {season}.")
        if not pitcher_rows:
            warnings.append(f"No pitcher season logs found for {season}.")
        return cls(batter_rows, pitcher_rows, batter_source, pitcher_source, warnings)

    def find(self, *, market: str, date_label: str, player: str, team: str, opponent: str = "", player_id: str = "") -> _LogMatch:
        is_pitcher = _clean(market).startswith("pitcher")
        rows = self.pitcher_rows if is_pitcher else self.batter_rows
        source = self.pitcher_source if is_pitcher else self.batter_source
        family = "pitcher" if is_pitcher else "batter"
        if not rows:
            return _LogMatch("missing_player", "No season log rows are available for this market family.", {}, source)
        target_date = date_label[:10]
        date_rows = [row for row in rows if _row_date(row) == target_date]
        if not date_rows:
            available_dates = sorted({_row_date(row) for row in rows if _row_date(row)})
            return _LogMatch(
                "missing_player",
                f"No {family} game logs found for date {target_date}. Available log dates: {_available_dates_summary(available_dates, target_date=target_date)}.",
                {},
                source,
            )
        target_id = _player_id(player_id)
        if target_id:
            id_candidates = [row for row in date_rows if _row_player_id(row) == target_id]
            id_match = _single_match(id_candidates, source)
            if id_match is not None:
                return id_match

        target = _player_norm(player)
        name_candidates = [row for row in date_rows if target and target in _row_player_norms(row, is_pitcher=is_pitcher)]
        if not name_candidates:
            sample_names = sorted({name for row in date_rows for name in _row_player_display_names(row, is_pitcher=is_pitcher) if name})[:8]
            return _LogMatch(
                "missing_player",
                f"No player game log matched {player!r} on {target_date}. Checked player_id={target_id or 'blank'}, team={_team_alias(team) or 'blank'}, sample log players: {', '.join(sample_names) or 'none'}.",
                {},
                source,
            )

        name_match = _single_match(name_candidates, source)
        if name_match is not None and name_match.status == "ok":
            return name_match

        target_team = _team_alias(team)
        team_candidates = [row for row in name_candidates if target_team and _row_team(row) == target_team]
        team_match = _single_match(team_candidates, source)
        if team_match is not None:
            return team_match

        target_opponent = _team_alias(opponent)
        opponent_candidates = [row for row in name_candidates if target_opponent and _row_team(row) == target_opponent]
        opponent_match = _single_match(opponent_candidates, source)
        if opponent_match is not None:
            return opponent_match

        return _LogMatch("ambiguous_match", "Multiple player game logs matched the feature row.", {}, source)


def _merged_existing_rows(paths: Sequence[Path]) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    sources: list[str] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for path in paths:
        path_rows = _read_csv(path)
        if not path_rows:
            continue
        sources.append(str(path).replace("\\", "/"))
        for row in path_rows:
            key = (*_match_identity(row), _row_player_id(row))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows, ";".join(sources)


def _first_existing_rows(paths: Sequence[Path]) -> tuple[list[dict[str, str]], str]:
    return _merged_existing_rows(paths)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError:
        return []


def _stat_value(row: Mapping[str, Any], stat_key: str) -> float | None:
    aliases = STAT_ALIASES.get(stat_key, (stat_key,))
    lower = {str(key).lower(): value for key, value in row.items()}
    for alias in aliases:
        value = lower.get(alias.lower())
        if value is None or value == "":
            continue
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _line_for_market(market: str, value: Any) -> float | None:
    explicit = _float_or_none(value)
    if explicit is not None:
        return explicit
    match = re.search(r"_(\d+)plus_", str(market or ""))
    if match:
        return float(int(match.group(1)) - 0.5)
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _planned_label_paths(output_dir: Path, date_label: str, output_format: str) -> dict[str, Path]:
    selected = _normal_format(output_format)
    paths: dict[str, Path] = {}
    if selected in {"csv", "both"}:
        paths["csv"] = output_dir / f"player_prop_labels_{date_label}.csv"
    if selected in {"json", "both"}:
        paths["json"] = output_dir / f"player_prop_labels_{date_label}.json"
    paths["manifest"] = output_dir / f"player_prop_label_manifest_{date_label}.json"
    return paths


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _only_label_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in LABEL_FIELD_ORDER}


def _normal_source(source: str) -> str:
    text = _clean(source).lower().replace("_", "-") or DEFAULT_SOURCE
    if text in {"edge", "edgeboard"}:
        return "edge-board"
    if text in {"player", "player-board"}:
        return "playerboard"
    return text if text in {"playerboard", "edge-board", "both"} else DEFAULT_SOURCE


def _normal_format(value: str) -> str:
    text = _clean(value).lower() or "both"
    return text if text in {"csv", "json", "both"} else "both"


def _display_path(path: Path, settings: Settings) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(settings.data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(settings.root_dir.resolve())).replace("\\", "/")
        except (OSError, ValueError):
            return str(path).replace("\\", "/")


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _match_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (_row_date(row), _first_player_norm(row), _row_team(row), _first_value(row, GAME_PK_FIELDS))


def _single_match(candidates: Sequence[dict[str, str]], source: str) -> _LogMatch | None:
    if not candidates:
        return None
    unique = {_match_identity(row) for row in candidates}
    if len(unique) > 1:
        return _LogMatch("ambiguous_match", "Multiple player game logs matched the feature row.", {}, source)
    return _LogMatch("ok", "Matched player game log.", candidates[0], source)


def _player_norm(value: Any) -> str:
    return _norm(_strip_player_market_suffix(value))


def _strip_player_market_suffix(value: Any) -> str:
    text = _clean(value)
    for suffix in PLAYER_MARKET_SUFFIXES:
        pattern = rf"\s+{re.escape(suffix)}$"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
    return text


def _row_date(row: Mapping[str, Any]) -> str:
    return _first_value(row, DATE_FIELDS)[:10]


def _row_player_id(row: Mapping[str, Any]) -> str:
    return _player_id(_first_value(row, PLAYER_ID_FIELDS))


def _row_team(row: Mapping[str, Any]) -> str:
    return _team_alias(_first_value(row, TEAM_FIELDS))


def _row_player_norms(row: Mapping[str, Any], *, is_pitcher: bool) -> set[str]:
    fields = PITCHER_NAME_FIELDS if is_pitcher else PLAYER_NAME_FIELDS
    return {_player_norm(value) for value in _values(row, fields) if _player_norm(value)}


def _row_player_display_names(row: Mapping[str, Any], *, is_pitcher: bool) -> list[str]:
    fields = PITCHER_NAME_FIELDS if is_pitcher else PLAYER_NAME_FIELDS
    seen: set[str] = set()
    names: list[str] = []
    for value in _values(row, fields):
        text = _strip_player_market_suffix(value)
        key = _player_norm(text)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(text)
    return names


def _first_player_norm(row: Mapping[str, Any]) -> str:
    for value in _values(row, PITCHER_NAME_FIELDS):
        text = _player_norm(value)
        if text:
            return text
    return ""


def _team_alias(value: Any) -> str:
    text = _clean(value).upper().replace(".", "")
    text = " ".join(text.split())
    if not text:
        return ""
    return TEAM_ALIASES.get(text, text)


def _player_id(value: Any) -> str:
    return _clean(value).lstrip("#")


def _norm(value: Any) -> str:
    text = _clean(value).lower().replace(".", "").replace(",", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first_value(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = _clean(row.get(key))
        if value:
            return value
    return ""


def _values(row: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = _clean(row.get(key))
        if value:
            values.append(value)
    return values


def _available_dates_summary(dates: Sequence[str], *, target_date: str = "") -> str:
    if not dates:
        return "none"
    if len(dates) <= 12:
        return ", ".join(dates)
    nearest: list[str] = []
    if target_date:
        before = [date for date in dates if date < target_date]
        after = [date for date in dates if date > target_date]
        if before:
            nearest.append(before[-1])
        if after:
            nearest.append(after[0])
    nearest_text = f"; nearest to requested date: {', '.join(nearest)}" if nearest else ""
    return f"{dates[0]}..{dates[-1]} ({len(dates)} dates{nearest_text})"


def _label_matching_warnings(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    missing_reasons = Counter(
        _clean(row.get("label_reason"))
        for row in rows
        if _clean(row.get("label_status")) == "missing_player" and _clean(row.get("label_reason"))
    )
    warnings: list[str] = []
    for reason, count in missing_reasons.most_common(5):
        warnings.append(f"Label matching diagnostic: {count} missing_player rows: {reason}")
    return warnings


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
