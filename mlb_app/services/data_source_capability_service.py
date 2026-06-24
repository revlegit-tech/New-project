from __future__ import annotations

import csv
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.contracts.feature_store_schema import feature_store_contract
from mlb_app.services.runtime_status_service import safe_relpath

SCHEMA_VERSION = "data-source-capability.v1"

CRITICAL_BOARD_GROUPS = ("market", "gameContext", "weather", "batterSavant", "pitcherSavant", "history")
TRAINING_GROUPS = CRITICAL_BOARD_GROUPS + ("labels",)
DEFAULT_BASELINE_LABEL_ROWS = 100
DEFAULT_PRODUCTION_LABEL_ROWS_PER_MARKET = 500


class DataSourceCapabilityService:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings
        self.min_baseline_label_rows = _int_from_env("MLB_BASELINE_LABEL_MIN_ROWS", DEFAULT_BASELINE_LABEL_ROWS)
        self.min_production_label_rows_per_market = _int_from_env(
            "MLB_PRODUCTION_LABEL_MIN_ROWS_PER_MARKET",
            DEFAULT_PRODUCTION_LABEL_ROWS_PER_MARKET,
        )

    def payload(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        target_date, mode = resolve_date_mode(date_label)
        selected_season = int(season or self.settings.current_season)
        sources = self._sources(target_date, selected_season)
        feature_groups = self._feature_groups(sources)
        recommendations = self._recommendations(sources, feature_groups)
        status = self._status(sources, feature_groups)
        audit = self._audit_from_groups(target_date, selected_season, feature_groups, sources)

        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": status,
            "season": selected_season,
            "date": target_date,
            "resolvedDateMode": mode,
            "sources": sources,
            "featureGroups": feature_groups,
            "featureStoreContract": feature_store_contract(),
            "featureAudit": audit,
            "recommendations": recommendations,
        }

    def audit_feature_availability(self, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        payload = self.payload(date_label=date_label, season=season)
        return dict(payload["featureAudit"])

    def capability_summary(self, *, date_label: str | None = None, season: int | None = None) -> dict[str, Any]:
        payload = self.payload(date_label=date_label, season=season)
        audit = dict(payload["featureAudit"])
        return {
            "featureStoreReady": bool(audit.get("readyForFeatureStore")),
            "readyForBoard": bool(audit.get("readyForBoard")),
            "readyForBaselineTraining": bool(audit.get("readyForBaselineTraining")),
            "readyForProductionTraining": bool(audit.get("readyForProductionTraining")),
            "missingCriticalFeatureGroups": list(audit.get("missingCriticalFeatureGroups") or []),
            "dataSourceCapabilityStatus": payload.get("status", "partial"),
        }

    def _sources(self, date_label: str, season: int) -> dict[str, dict[str, Any]]:
        data = self.settings.data_dir
        root = self.settings.root_dir
        return {
            "proplineProps": self._csv_source(
                name="proplineProps",
                paths=[data / "odds" / f"propline_props_{date_label}.csv"],
                modules=[root / "tools" / "fetch_propline_props.py", root / "mlb_app" / "integrations" / "propline" / "client.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="PropLine props collector",
                notes="Player prop offers used to seed board rows.",
            ),
            "actionNetworkOdds": self._glob_source(
                name="actionNetworkOdds",
                patterns=[
                    data / "warehouse" / "normalized" / "odds" / f"actionnetwork_all_markets_{date_label}*.csv",
                    data / "warehouse" / "normalized" / "actionnetwork" / f"*{date_label}*.csv",
                ],
                modules=[root / "scripts" / "collect_actionnetwork_odds.py", root / "mlb_app" / "services" / "actionnetwork_odds_movement_service.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="ActionNetwork normalized snapshot workflow",
                notes="Normalized odds snapshots and movement features.",
            ),
            "gameMarkets": self._glob_source(
                name="gameMarkets",
                patterns=[
                    data / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv",
                    data / "warehouse" / "game_context" / f"*{date_label}*",
                    data / "warehouse" / "game_odds" / f"*{date_label}*.csv",
                    data / "game_odds" / f"*{date_label}*.csv",
                ],
                modules=[root / "tools" / "phase17_game_context_markets.py", root / "tools" / "phase18_context_qa.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Phase 17/18 game context tools",
                notes="Schedule, venue, park, probable pitcher, and game-market context.",
            ),
            "theOddsApi": self._glob_source(
                name="theOddsApi",
                patterns=[data / "warehouse" / "oddsapi" / f"*{date_label}*", data / "oddsapi" / f"*{date_label}*"],
                modules=[root / "tools" / "fetch_phase17_context_from_apis.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Optional The Odds API path",
                notes="Optional fallback for game moneyline and total context.",
            ),
            "oddsPapi": self._glob_source(
                name="oddsPapi",
                patterns=[data / "warehouse" / "oddspapi" / f"*{date_label}*", data / "audit" / f"phase22_oddspapi_clv_{date_label}.json"],
                modules=[root / "oddspapi_current_game_markets_latest.py", root / "tools" / "phase22_oddspapi_clv.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Optional OddsPapi snapshot path",
                notes="Optional fixture/game-market snapshots and CLV audit artifacts.",
            ),
            "mlbStatsApi": self._glob_source(
                name="mlbStatsApi",
                patterns=[
                    data / "warehouse" / "raw" / "statsapi" / f"*{date_label}*",
                    data / "cloud" / "season_logs" / f"*_game_logs_{season}.csv",
                ],
                modules=[root / "mlb_app" / "integrations" / "statsapi" / "warehouse_sync.py"],
                pregame_safe=True,
                postgame_only=True,
                collected_by="MLB StatsAPI schedule/boxscore sync",
                notes="Schedule is pregame-safe; boxscores and game logs are post-game truth sources.",
            ),
            "weather": self._glob_source(
                name="weather",
                patterns=[data / "cache" / "weather" / f"*{season}*.csv", data / "warehouse" / "weather" / f"*{date_label}*", data / f"weather_{date_label}.json"],
                modules=[root / "weather_collector.py", root / "tools" / "phase17_patch_openmeteo_coordinate_loader.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Open-Meteo weather collector",
                notes="Venue-based weather forecast features.",
            ),
            "savant": self._glob_source(
                name="savant",
                patterns=[
                    data / "cache" / "savant" / f"*{season}*",
                    data / "warehouse" / "statcast" / f"*{season}*",
                    data / "cloud" / "season_logs" / f"batter_game_logs_{season}.csv",
                    data / "cloud" / "season_logs" / f"pitcher_game_logs_{season}.csv",
                ],
                modules=[root / "savant_features.py", root / "mlb_app" / "services" / "baseball_savant_feature_service.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="pybaseball/Savant/Statcast cache",
                notes="Batter and pitcher quality metrics derived from historical Statcast data.",
            ),
            "umpires": self._glob_source(
                name="umpires",
                patterns=[data / "cache" / "umpires" / f"*{season}*", data / "warehouse" / "umpires" / f"*{date_label}*", data / f"umpires_{season}.csv"],
                modules=[root / "umpire_collector.py", root / "check_umpire_coverage.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Umpire collector/cache",
                notes="Projected/assigned umpire context when available.",
            ),
            "playerboard": self._glob_source(
                name="playerboard",
                patterns=[data / "playerboard" / f"*{season}*.csv", data / "snapshots" / f"*{date_label}*", data / "edge_board" / f"*{date_label}*.json"],
                modules=[root / "playerboard.py", root / "mlb_app" / "services" / "playerboard_builder.py"],
                pregame_safe=True,
                postgame_only=False,
                collected_by="Playerboard serving snapshots",
                notes="Serving board snapshots assembled from pregame source artifacts.",
            ),
            "labels": self._glob_source(
                name="labels",
                patterns=[
                    data / "labels" / f"*{season}*.csv",
                    data / "training" / f"*{season}*.csv",
                    data / "backtests" / f"*{season}*.csv",
                    data / "warehouse" / "normalized" / "actionnetwork" / f"*labels*{date_label}*.csv",
                ],
                modules=[root / "scripts" / "build_player_prop_labels.py", root / "playerboard_backtest.py"],
                pregame_safe=False,
                postgame_only=True,
                collected_by="Labels/outcomes/backtest builders",
                notes="Post-game outcomes for training/evaluation only.",
            ),
        }

    def _csv_source(
        self,
        *,
        name: str,
        paths: list[Path],
        modules: list[Path],
        pregame_safe: bool,
        postgame_only: bool,
        collected_by: str,
        notes: str,
    ) -> dict[str, Any]:
        existing = [path for path in paths if path.is_file()]
        latest = max(existing, key=lambda path: path.stat().st_mtime, default=None)
        return self._source_payload(name, existing, modules, pregame_safe, postgame_only, collected_by, notes, latest)

    def _glob_source(
        self,
        *,
        name: str,
        patterns: list[Path],
        modules: list[Path],
        pregame_safe: bool,
        postgame_only: bool,
        collected_by: str,
        notes: str,
    ) -> dict[str, Any]:
        files: list[Path] = []
        for pattern in patterns:
            files.extend(path for path in pattern.parent.glob(pattern.name) if path.is_file())
        existing = sorted(set(files))
        latest = max(existing, key=lambda path: path.stat().st_mtime, default=None)
        return self._source_payload(name, existing, modules, pregame_safe, postgame_only, collected_by, notes, latest)

    def _source_payload(
        self,
        name: str,
        files: list[Path],
        modules: list[Path],
        pregame_safe: bool,
        postgame_only: bool,
        collected_by: str,
        notes: str,
        latest: Path | None,
    ) -> dict[str, Any]:
        module_paths = [path for path in modules if path.is_file()]
        rows = _count_rows(latest) if latest is not None else 0
        total_rows = sum(_count_rows(path) for path in files)
        return {
            "name": name,
            "status": "available" if files else "missing",
            "available": bool(files),
            "fileCount": len(files),
            "rowCount": rows,
            "totalRowCount": total_rows,
            "latestPath": safe_relpath(latest, self.settings.root_dir) if latest else "",
            "latestModifiedAt": _mtime_iso(latest) if latest else "",
            "samplePaths": [safe_relpath(path, self.settings.root_dir) for path in files[-5:]],
            "collectorModulesPresent": [safe_relpath(path, self.settings.root_dir) for path in module_paths],
            "collectorModuleCount": len(module_paths),
            "pregameSafe": pregame_safe,
            "postgameOnly": postgame_only,
            "collectedBy": collected_by,
            "notes": notes,
        }

    def _feature_groups(self, sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            "market": self._group("market", ["proplineProps", "actionNetworkOdds"], sources, pregame_safe=True, critical=True),
            "gameContext": self._group("gameContext", ["gameMarkets", "theOddsApi", "oddsPapi", "mlbStatsApi"], sources, pregame_safe=True, critical=True),
            "weather": self._group("weather", ["weather"], sources, pregame_safe=True, critical=True),
            "batterSavant": self._group("batterSavant", ["savant"], sources, pregame_safe=True, critical=True),
            "pitcherSavant": self._group("pitcherSavant", ["savant"], sources, pregame_safe=True, critical=True),
            "umpire": self._group("umpire", ["umpires"], sources, pregame_safe=True, critical=False),
            "history": self._group("history", ["mlbStatsApi", "playerboard"], sources, pregame_safe=True, critical=True),
            "labels": self._group("labels", ["labels"], sources, pregame_safe=False, critical=False),
        }

    def _group(self, name: str, source_keys: list[str], sources: dict[str, dict[str, Any]], *, pregame_safe: bool, critical: bool) -> dict[str, Any]:
        available_sources = [key for key in source_keys if sources.get(key, {}).get("available")]
        latest_times = [str(sources[key].get("latestModifiedAt") or "") for key in available_sources]
        return {
            "name": name,
            "status": "available" if available_sources else "missing",
            "available": bool(available_sources),
            "pregameSafe": pregame_safe,
            "criticalForBoard": critical,
            "sourceKeys": source_keys,
            "availableSourceKeys": available_sources,
            "latestModifiedAt": max(latest_times) if latest_times else "",
        }

    def _audit_from_groups(
        self,
        date_label: str,
        season: int,
        feature_groups: dict[str, dict[str, Any]],
        sources: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        expected = list(feature_groups)
        available = [name for name, group in feature_groups.items() if group.get("available")]
        missing = [name for name in expected if name not in available]
        missing_critical = [name for name in CRITICAL_BOARD_GROUPS if name in missing]
        freshness = {
            name: {
                "latestModifiedAt": group.get("latestModifiedAt", ""),
                "status": group.get("status", "missing"),
            }
            for name, group in feature_groups.items()
        }
        ready_for_board = not missing_critical
        ready_for_feature_store = ready_for_board
        label_sufficiency = self._label_sufficiency(sources)
        training_validation = self._training_validation(sources, feature_groups, missing_critical, label_sufficiency)
        return {
            "schemaVersion": "feature-availability-audit.v1",
            "date": date_label,
            "season": season,
            "expectedFeatureGroups": expected,
            "availableFeatureGroups": available,
            "missingFeatureGroups": missing,
            "missingCriticalFeatureGroups": missing_critical,
            "freshness": freshness,
            "readyForBoard": ready_for_board,
            "readyForFeatureStore": ready_for_feature_store,
            "readyForBaselineTraining": bool(ready_for_feature_store and label_sufficiency["baselineReady"]),
            "readyForProductionTraining": bool(
                ready_for_feature_store
                and label_sufficiency["baselineReady"]
                and training_validation["productionReady"]
            ),
            "readyForMLTraining": bool(ready_for_feature_store and label_sufficiency["baselineReady"]),
            "labelSufficiency": label_sufficiency,
            "trainingValidation": training_validation,
            "modelTrainingTriggered": False,
            "externalApiCallsMade": False,
            "sourceCount": len(sources),
        }

    def _recommendations(self, sources: dict[str, dict[str, Any]], feature_groups: dict[str, dict[str, Any]]) -> list[str]:
        recommendations: list[str] = []
        label_sufficiency = self._label_sufficiency(sources)
        training_validation = self._training_validation(
            sources,
            feature_groups,
            [name for name in CRITICAL_BOARD_GROUPS if not feature_groups.get(name, {}).get("available")],
            label_sufficiency,
        )
        for name, group in feature_groups.items():
            if group.get("criticalForBoard") and not group.get("available"):
                recommendations.append(f"Missing critical pregame feature group: {name}.")
        if not sources.get("gameMarkets", {}).get("available"):
            recommendations.append("Normalized game-market artifacts are missing; game-market context should be collected before modeling.")
        if not sources.get("labels", {}).get("available"):
            recommendations.append("No label/outcome artifacts found; ML training readiness remains false.")
        elif label_sufficiency["totalLabelRows"] < label_sufficiency["baselineMinRows"]:
            recommendations.append(
                f"Label row count is below baseline threshold: {label_sufficiency['totalLabelRows']} < {label_sufficiency['baselineMinRows']}."
            )
        if not training_validation["productionReady"]:
            recommendations.append("Production training requires per-market two-class validation and calibration/backtest artifacts.")
        if not sources.get("umpires", {}).get("available"):
            recommendations.append("Umpire features are optional for board readiness but should be backfilled for model training.")
        return recommendations

    def _label_sufficiency(self, sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
        labels = sources.get("labels", {})
        artifact_count = int(labels.get("fileCount") or 0)
        total_rows = int(labels.get("totalRowCount") or labels.get("rowCount") or 0)
        leakage_ok = bool(labels.get("postgameOnly")) and not bool(labels.get("pregameSafe"))
        return {
            "labelsAvailable": bool(labels.get("available")),
            "labelArtifactCount": artifact_count,
            "totalLabelRows": total_rows,
            "baselineMinRows": self.min_baseline_label_rows,
            "productionMinRowsPerMarket": self.min_production_label_rows_per_market,
            "leakagePolicyOk": leakage_ok,
            "baselineReady": bool(labels.get("available") and artifact_count >= 1 and total_rows >= self.min_baseline_label_rows and leakage_ok),
        }

    def _training_validation(
        self,
        sources: dict[str, dict[str, Any]],
        feature_groups: dict[str, dict[str, Any]],
        missing_critical: list[str],
        label_sufficiency: dict[str, Any],
    ) -> dict[str, Any]:
        backtest_artifacts = self._has_backtest_artifacts()
        calibration_artifacts = self._has_calibration_artifacts()
        two_class_validation = self._has_two_class_validation_artifacts()
        per_market_validation = self._has_per_market_label_validation_artifacts()
        return {
            "perMarketLabelValidationAvailable": per_market_validation,
            "twoClassTargetValidationAvailable": two_class_validation,
            "twoClassTargetValidationConfirmed": False,
            "calibrationArtifactsAvailable": calibration_artifacts,
            "backtestArtifactsAvailable": backtest_artifacts,
            "productionMinRowsPerMarket": label_sufficiency["productionMinRowsPerMarket"],
            "missingCriticalFeatureGroups": missing_critical,
            "productionReady": bool(
                label_sufficiency["baselineReady"]
                and per_market_validation
                and two_class_validation
                and calibration_artifacts
                and backtest_artifacts
                and not missing_critical
            ),
        }

    def _has_backtest_artifacts(self) -> bool:
        return any((self.settings.data_dir / "backtests").glob("*.csv")) or any((self.settings.data_dir / "backtests").glob("*.json"))

    def _has_calibration_artifacts(self) -> bool:
        candidates = [
            self.settings.data_dir / "calibration",
            self.settings.data_dir / "models",
            self.settings.model_dir,
        ]
        patterns = ("*calibration*.json", "*calibration*.csv", "*backtest*calibration*.json")
        return any(path.is_file() for directory in candidates for pattern in patterns for path in directory.glob(pattern) if directory.exists())

    def _has_two_class_validation_artifacts(self) -> bool:
        candidates = [
            self.settings.data_dir / "quality",
            self.settings.data_dir / "training",
            self.settings.data_dir / "audit",
        ]
        patterns = ("*two_class*.json", "*two-class*.json", "*class_balance*.json", "*label_validation*.json")
        return any(path.is_file() for directory in candidates for pattern in patterns for path in directory.glob(pattern) if directory.exists())

    def _has_per_market_label_validation_artifacts(self) -> bool:
        candidates = [
            self.settings.data_dir / "quality",
            self.settings.data_dir / "training",
            self.settings.data_dir / "audit",
        ]
        patterns = ("*per_market*.json", "*market_label*.json", "*label_validation*.json")
        return any(path.is_file() for directory in candidates for pattern in patterns for path in directory.glob(pattern) if directory.exists())

    def _status(self, sources: dict[str, dict[str, Any]], feature_groups: dict[str, dict[str, Any]]) -> str:
        if not any(source.get("available") for source in sources.values()):
            return "partial"
        if any(feature_groups[name].get("available") is False for name in CRITICAL_BOARD_GROUPS):
            return "partial"
        return "ok"


def audit_feature_availability(date_label: str | None = None, season: int | None = None, *, settings: Settings = default_settings) -> dict[str, Any]:
    return DataSourceCapabilityService(settings).audit_feature_availability(date_label=date_label, season=season)


def resolve_date_mode(value: str | None) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return datetime.now().astimezone().date().isoformat(), "default"
    if text.lower() == "today":
        return datetime.now().astimezone().date().isoformat(), "today"
    return text[:10], "explicit"


def _count_rows(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    if path.suffix.lower() == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return sum(1 for _ in csv.DictReader(handle))
        except Exception:
            return 0
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("rows", "games", "props", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return len(value)
            return 1
    return 0


def _int_from_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(str(raw).strip()) if str(raw).strip() else fallback
    except (TypeError, ValueError):
        return fallback


def _mtime_iso(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
