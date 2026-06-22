from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, json_text, utc_now_text


class HistoricalGameOddsRepository:
    """Warehouse repository for historical game-level odds and grades."""

    def __init__(self, db: WarehouseDatabase, *, settings: Settings = default_settings) -> None:
        self.db = db
        self.settings = settings

    def initialize_schema(self) -> None:
        self.db.initialize()

    def upsert_import_manifest(self, manifest: Mapping[str, Any]) -> int:
        row = _import_manifest_row(manifest)
        with self.db.session(write=True) as session:
            session.execute(
                """
                INSERT INTO historical_game_odds_imports(
                  import_id, source_file, started_at, finished_at, status,
                  games_read, games_imported, line_rows_imported,
                  feature_rows_written, grade_rows_written, warnings_json,
                  errors_json, created_at
                ) VALUES (
                  :import_id, :source_file, :started_at, :finished_at, :status,
                  :games_read, :games_imported, :line_rows_imported,
                  :feature_rows_written, :grade_rows_written, :warnings_json,
                  :errors_json, :created_at
                )
                ON CONFLICT(import_id) DO UPDATE SET
                  source_file = excluded.source_file,
                  started_at = excluded.started_at,
                  finished_at = excluded.finished_at,
                  status = excluded.status,
                  games_read = excluded.games_read,
                  games_imported = excluded.games_imported,
                  line_rows_imported = excluded.line_rows_imported,
                  feature_rows_written = excluded.feature_rows_written,
                  grade_rows_written = excluded.grade_rows_written,
                  warnings_json = excluded.warnings_json,
                  errors_json = excluded.errors_json
                """,
                row,
            )
        return 1

    def upsert_games(self, games: Sequence[Mapping[str, Any]]) -> int:
        values = [_game_row(row) for row in games]
        if not values:
            return 0
        with self.db.session(write=True) as session:
            session.executemany(
                """
                INSERT INTO historical_game_odds_games(
                  game_id, game_date, season, start_time_utc, game_type, venue,
                  away_team, home_team, away_score, home_score, game_status,
                  created_at, updated_at
                ) VALUES (
                  :game_id, :game_date, :season, :start_time_utc, :game_type, :venue,
                  :away_team, :home_team, :away_score, :home_score, :game_status,
                  :created_at, :updated_at
                )
                ON CONFLICT(game_id) DO UPDATE SET
                  game_date = excluded.game_date,
                  season = excluded.season,
                  start_time_utc = excluded.start_time_utc,
                  game_type = excluded.game_type,
                  venue = excluded.venue,
                  away_team = excluded.away_team,
                  home_team = excluded.home_team,
                  away_score = excluded.away_score,
                  home_score = excluded.home_score,
                  game_status = excluded.game_status,
                  updated_at = excluded.updated_at
                """,
                values,
            )
        return len(values)

    def upsert_lines(self, lines: Sequence[Mapping[str, Any]]) -> int:
        values = [_line_row(row) for row in lines]
        if not values:
            return 0
        with self.db.session(write=True) as session:
            session.executemany(
                """
                INSERT INTO historical_game_odds_lines(
                  id, game_id, game_date, sportsbook, market, side,
                  opening_odds, current_odds, opening_line, current_line,
                  opening_implied_prob, current_implied_prob,
                  opening_no_vig_prob, current_no_vig_prob,
                  odds_movement, line_movement, quality_flags_json,
                  created_at, updated_at
                ) VALUES (
                  :id, :game_id, :game_date, :sportsbook, :market, :side,
                  :opening_odds, :current_odds, :opening_line, :current_line,
                  :opening_implied_prob, :current_implied_prob,
                  :opening_no_vig_prob, :current_no_vig_prob,
                  :odds_movement, :line_movement, :quality_flags_json,
                  :created_at, :updated_at
                )
                ON CONFLICT(game_id, sportsbook, market, side) DO UPDATE SET
                  game_date = excluded.game_date,
                  opening_odds = excluded.opening_odds,
                  current_odds = excluded.current_odds,
                  opening_line = excluded.opening_line,
                  current_line = excluded.current_line,
                  opening_implied_prob = excluded.opening_implied_prob,
                  current_implied_prob = excluded.current_implied_prob,
                  opening_no_vig_prob = excluded.opening_no_vig_prob,
                  current_no_vig_prob = excluded.current_no_vig_prob,
                  odds_movement = excluded.odds_movement,
                  line_movement = excluded.line_movement,
                  quality_flags_json = excluded.quality_flags_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )
        return len(values)

    def upsert_features(self, features: Sequence[Mapping[str, Any]]) -> int:
        values = [_feature_row(row) for row in features]
        if not values:
            return 0
        with self.db.session(write=True) as session:
            session.executemany(
                """
                INSERT INTO historical_game_market_features(
                  game_id, game_date, season, away_team, home_team, venue,
                  consensus_open_total, consensus_current_total, total_line_movement,
                  home_open_moneyline_consensus, away_open_moneyline_consensus,
                  home_current_moneyline_consensus, away_current_moneyline_consensus,
                  home_no_vig_win_prob_open, away_no_vig_win_prob_open,
                  home_no_vig_win_prob_current, away_no_vig_win_prob_current,
                  favorite_team_open, favorite_team_current, book_count_moneyline,
                  book_count_total, book_count_runline, market_disagreement_score,
                  quality_flags_json, created_at, updated_at
                ) VALUES (
                  :game_id, :game_date, :season, :away_team, :home_team, :venue,
                  :consensus_open_total, :consensus_current_total, :total_line_movement,
                  :home_open_moneyline_consensus, :away_open_moneyline_consensus,
                  :home_current_moneyline_consensus, :away_current_moneyline_consensus,
                  :home_no_vig_win_prob_open, :away_no_vig_win_prob_open,
                  :home_no_vig_win_prob_current, :away_no_vig_win_prob_current,
                  :favorite_team_open, :favorite_team_current, :book_count_moneyline,
                  :book_count_total, :book_count_runline, :market_disagreement_score,
                  :quality_flags_json, :created_at, :updated_at
                )
                ON CONFLICT(game_id) DO UPDATE SET
                  game_date = excluded.game_date,
                  season = excluded.season,
                  away_team = excluded.away_team,
                  home_team = excluded.home_team,
                  venue = excluded.venue,
                  consensus_open_total = excluded.consensus_open_total,
                  consensus_current_total = excluded.consensus_current_total,
                  total_line_movement = excluded.total_line_movement,
                  home_open_moneyline_consensus = excluded.home_open_moneyline_consensus,
                  away_open_moneyline_consensus = excluded.away_open_moneyline_consensus,
                  home_current_moneyline_consensus = excluded.home_current_moneyline_consensus,
                  away_current_moneyline_consensus = excluded.away_current_moneyline_consensus,
                  home_no_vig_win_prob_open = excluded.home_no_vig_win_prob_open,
                  away_no_vig_win_prob_open = excluded.away_no_vig_win_prob_open,
                  home_no_vig_win_prob_current = excluded.home_no_vig_win_prob_current,
                  away_no_vig_win_prob_current = excluded.away_no_vig_win_prob_current,
                  favorite_team_open = excluded.favorite_team_open,
                  favorite_team_current = excluded.favorite_team_current,
                  book_count_moneyline = excluded.book_count_moneyline,
                  book_count_total = excluded.book_count_total,
                  book_count_runline = excluded.book_count_runline,
                  market_disagreement_score = excluded.market_disagreement_score,
                  quality_flags_json = excluded.quality_flags_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )
        return len(values)

    def upsert_grades(self, grades: Sequence[Mapping[str, Any]]) -> int:
        values = [_grade_row(row) for row in grades]
        if not values:
            return 0
        with self.db.session(write=True) as session:
            session.executemany(
                """
                INSERT INTO historical_game_market_grades(
                  id, game_id, game_date, sportsbook, market, side, line,
                  odds, result, push_flag, profit_1u, closing_line_value,
                  graded_at
                ) VALUES (
                  :id, :game_id, :game_date, :sportsbook, :market, :side, :line,
                  :odds, :result, :push_flag, :profit_1u, :closing_line_value,
                  :graded_at
                )
                ON CONFLICT(game_id, sportsbook, market, side) DO UPDATE SET
                  game_date = excluded.game_date,
                  line = excluded.line,
                  odds = excluded.odds,
                  result = excluded.result,
                  push_flag = excluded.push_flag,
                  profit_1u = excluded.profit_1u,
                  closing_line_value = excluded.closing_line_value,
                  graded_at = excluded.graded_at
                """,
                values,
            )
        return len(values)

    def query_lines_by_date(self, date_label: str) -> list[dict[str, Any]]:
        selected_date = clean(date_label) or self.latest_game_date()
        if not selected_date:
            return []
        with self.db.session() as session:
            rows = session.fetch_all(
                """
                SELECT * FROM historical_game_odds_lines
                WHERE game_date = :game_date
                ORDER BY game_date ASC, game_id ASC, market ASC, sportsbook ASC, side ASC
                """,
                {"game_date": selected_date},
            )
        return [_decode_json_fields(row) for row in rows]

    def query_features_by_date(self, date_label: str) -> list[dict[str, Any]]:
        selected_date = clean(date_label) or self.latest_game_date()
        if not selected_date:
            return []
        with self.db.session() as session:
            rows = session.fetch_all(
                """
                SELECT * FROM historical_game_market_features
                WHERE game_date = :game_date
                ORDER BY game_date ASC, away_team ASC, home_team ASC
                """,
                {"game_date": selected_date},
            )
        return [_decode_json_fields(row) for row in rows]

    def query_grades_by_date(self, date_label: str) -> list[dict[str, Any]]:
        selected_date = clean(date_label) or self.latest_game_date()
        if not selected_date:
            return []
        with self.db.session() as session:
            rows = session.fetch_all(
                """
                SELECT * FROM historical_game_market_grades
                WHERE game_date = :game_date
                ORDER BY game_date ASC, game_id ASC, market ASC, sportsbook ASC, side ASC
                """,
                {"game_date": selected_date},
            )
        return rows

    def feature_by_matchup(self, *, date_label: str, team: str, opponent: str) -> dict[str, Any] | None:
        date_value = clean(date_label)
        team_value = clean(team).upper()
        opponent_value = clean(opponent).upper()
        if not date_value or not team_value or not opponent_value:
            return None
        with self.db.session() as session:
            row = session.fetch_one(
                """
                SELECT * FROM historical_game_market_features
                WHERE game_date = :game_date
                  AND (
                    (away_team = :team AND home_team = :opponent)
                    OR (away_team = :opponent AND home_team = :team)
                  )
                LIMIT 1
                """,
                {"game_date": date_value, "team": team_value, "opponent": opponent_value},
            )
        return _decode_json_fields(row) if row else None

    def latest_game_date(self) -> str:
        with self.db.session() as session:
            row = session.fetch_one("SELECT game_date FROM historical_game_odds_games ORDER BY game_date DESC LIMIT 1")
        return clean(row.get("game_date")) if row else ""

    def latest_feature_date(self) -> str:
        with self.db.session() as session:
            row = session.fetch_one(
                """
                SELECT game_date FROM historical_game_market_features
                ORDER BY game_date DESC
                LIMIT 1
                """
            )
        return clean(row.get("game_date")) if row else ""

    def status(self, *, source_file: str | Path | None = None) -> dict[str, Any]:
        health = self.db.health_check().to_dict()
        source_path = Path(source_file) if source_file else self.settings.data_dir / "external" / "mlb_odds_dataset.json"
        warnings: list[str] = []
        if not source_path.exists():
            warnings.append(f"Historical game odds source file is missing: {_display_path(source_path, self.settings.data_dir)}")
        result = {
            "enabled": bool(health.get("enabled")),
            "reachable": bool(health.get("reachable")),
            "dialect": clean(health.get("dialect")),
            "reason": clean(health.get("reason")),
            "error": clean(health.get("error")),
            "games": 0,
            "line_rows": 0,
            "feature_rows": 0,
            "grade_rows": 0,
            "latest_import_at": "",
            "latest_import_status": "",
            "source_file_present": source_path.exists(),
            "warnings": warnings,
        }
        if not result["enabled"] or not result["reachable"]:
            return result
        try:
            result.update(
                {
                    "games": self._count("historical_game_odds_games"),
                    "line_rows": self._count("historical_game_odds_lines"),
                    "feature_rows": self._count("historical_game_market_features"),
                    "grade_rows": self._count("historical_game_market_grades"),
                }
            )
            latest = self.latest_import()
            if latest:
                result["latest_import_at"] = clean(latest.get("finished_at")) or clean(latest.get("started_at"))
                result["latest_import_status"] = clean(latest.get("status"))
                result["warnings"].extend(_json_list(latest.get("warnings_json")))
        except Exception as error:
            result["reachable"] = False
            result["reason"] = "historical_game_odds_unavailable"
            result["error"] = f"{type(error).__name__}: {error}"
            result["warnings"].append("Historical game odds warehouse tables are not initialized.")
        return result

    def latest_import(self) -> dict[str, Any] | None:
        with self.db.session() as session:
            return session.fetch_one(
                """
                SELECT * FROM historical_game_odds_imports
                ORDER BY started_at DESC, created_at DESC
                LIMIT 1
                """
            )

    def _count(self, table: str) -> int:
        if table not in {
            "historical_game_odds_games",
            "historical_game_odds_lines",
            "historical_game_market_features",
            "historical_game_market_grades",
        }:
            return 0
        with self.db.session() as session:
            row = session.fetch_one(f"SELECT COUNT(*) AS row_count FROM {table}")
        return int(row.get("row_count") or 0) if row else 0


def _import_manifest_row(manifest: Mapping[str, Any]) -> dict[str, Any]:
    now = clean(manifest.get("created_at")) or utc_now_text()
    return {
        "import_id": clean(manifest.get("import_id")),
        "source_file": clean(manifest.get("source_file")),
        "started_at": clean(manifest.get("started_at")),
        "finished_at": clean(manifest.get("finished_at")),
        "status": clean(manifest.get("status")),
        "games_read": _int(manifest.get("games_read")),
        "games_imported": _int(manifest.get("games_imported")),
        "line_rows_imported": _int(manifest.get("line_rows_imported")),
        "feature_rows_written": _int(manifest.get("feature_rows_written")),
        "grade_rows_written": _int(manifest.get("grade_rows_written")),
        "warnings_json": json_text(manifest.get("warnings"), []),
        "errors_json": json_text(manifest.get("errors"), []),
        "created_at": now,
    }


def _game_row(row: Mapping[str, Any]) -> dict[str, Any]:
    now = clean(row.get("updated_at")) or utc_now_text()
    return {
        "game_id": clean(row.get("game_id")),
        "game_date": clean(row.get("game_date")),
        "season": _int(row.get("season")),
        "start_time_utc": clean(row.get("start_time_utc")),
        "game_type": clean(row.get("game_type")),
        "venue": clean(row.get("venue")),
        "away_team": clean(row.get("away_team")).upper(),
        "home_team": clean(row.get("home_team")).upper(),
        "away_score": _optional_int(row.get("away_score")),
        "home_score": _optional_int(row.get("home_score")),
        "game_status": clean(row.get("game_status")),
        "created_at": clean(row.get("created_at")) or now,
        "updated_at": now,
    }


def _line_row(row: Mapping[str, Any]) -> dict[str, Any]:
    now = clean(row.get("updated_at")) or utc_now_text()
    return {
        "id": clean(row.get("id")),
        "game_id": clean(row.get("game_id")),
        "game_date": clean(row.get("game_date")),
        "sportsbook": clean(row.get("sportsbook")),
        "market": clean(row.get("market")),
        "side": clean(row.get("side")),
        "opening_odds": _optional_int(row.get("opening_odds")),
        "current_odds": _optional_int(row.get("current_odds")),
        "opening_line": _optional_float(row.get("opening_line")),
        "current_line": _optional_float(row.get("current_line")),
        "opening_implied_prob": _optional_float(row.get("opening_implied_prob")),
        "current_implied_prob": _optional_float(row.get("current_implied_prob")),
        "opening_no_vig_prob": _optional_float(row.get("opening_no_vig_prob")),
        "current_no_vig_prob": _optional_float(row.get("current_no_vig_prob")),
        "odds_movement": _optional_float(row.get("odds_movement")),
        "line_movement": _optional_float(row.get("line_movement")),
        "quality_flags_json": json_text(row.get("quality_flags"), []),
        "created_at": clean(row.get("created_at")) or now,
        "updated_at": now,
    }


def _feature_row(row: Mapping[str, Any]) -> dict[str, Any]:
    now = clean(row.get("updated_at")) or utc_now_text()
    return {
        "game_id": clean(row.get("game_id")),
        "game_date": clean(row.get("game_date")),
        "season": _int(row.get("season")),
        "away_team": clean(row.get("away_team")).upper(),
        "home_team": clean(row.get("home_team")).upper(),
        "venue": clean(row.get("venue")),
        "consensus_open_total": _optional_float(row.get("consensus_open_total")),
        "consensus_current_total": _optional_float(row.get("consensus_current_total")),
        "total_line_movement": _optional_float(row.get("total_line_movement")),
        "home_open_moneyline_consensus": _optional_float(row.get("home_open_moneyline_consensus")),
        "away_open_moneyline_consensus": _optional_float(row.get("away_open_moneyline_consensus")),
        "home_current_moneyline_consensus": _optional_float(row.get("home_current_moneyline_consensus")),
        "away_current_moneyline_consensus": _optional_float(row.get("away_current_moneyline_consensus")),
        "home_no_vig_win_prob_open": _optional_float(row.get("home_no_vig_win_prob_open")),
        "away_no_vig_win_prob_open": _optional_float(row.get("away_no_vig_win_prob_open")),
        "home_no_vig_win_prob_current": _optional_float(row.get("home_no_vig_win_prob_current")),
        "away_no_vig_win_prob_current": _optional_float(row.get("away_no_vig_win_prob_current")),
        "favorite_team_open": clean(row.get("favorite_team_open")).upper(),
        "favorite_team_current": clean(row.get("favorite_team_current")).upper(),
        "book_count_moneyline": _int(row.get("book_count_moneyline")),
        "book_count_total": _int(row.get("book_count_total")),
        "book_count_runline": _int(row.get("book_count_runline")),
        "market_disagreement_score": _optional_float(row.get("market_disagreement_score")),
        "quality_flags_json": json_text(row.get("quality_flags"), []),
        "created_at": clean(row.get("created_at")) or now,
        "updated_at": now,
    }


def _grade_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": clean(row.get("id")),
        "game_id": clean(row.get("game_id")),
        "game_date": clean(row.get("game_date")),
        "sportsbook": clean(row.get("sportsbook")),
        "market": clean(row.get("market")),
        "side": clean(row.get("side")),
        "line": _optional_float(row.get("line")),
        "odds": _optional_int(row.get("odds")),
        "result": clean(row.get("result")),
        "push_flag": 1 if bool(row.get("push_flag")) else 0,
        "profit_1u": _optional_float(row.get("profit_1u")),
        "closing_line_value": _optional_float(row.get("closing_line_value")),
        "graded_at": clean(row.get("graded_at")) or utc_now_text(),
    }


def _decode_json_fields(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    result = dict(row)
    if "quality_flags_json" in result:
        result["quality_flags"] = _json_list(result.get("quality_flags_json"))
        result.pop("quality_flags_json", None)
    return result


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    if isinstance(value, str):
        try:
            raw = json.loads(value or "[]")
            if isinstance(raw, list):
                return [clean(item) for item in raw if clean(item)]
        except json.JSONDecodeError:
            return []
    return []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value).replace("+", "")))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def _display_path(path: Path, data_dir: Path) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")
