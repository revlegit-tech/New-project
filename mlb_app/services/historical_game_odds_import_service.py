from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.historical_game_odds_repository import HistoricalGameOddsRepository
from mlb_app.repositories.warehouse_utils import clean, json_text, stable_id, utc_now_text
from mlb_app.services.game_market_grading_service import GameMarketGradingService

HISTORICAL_GAME_ODDS_SCHEMA_VERSION = "historical-game-odds.v1"
DEFAULT_SOURCE_RELATIVE_PATH = Path("external") / "mlb_odds_dataset.json"
DEFAULT_EXPORT_RELATIVE_DIR = Path("warehouse") / "historical_game_odds"
LEAKAGE_FORBIDDEN_FEATURE_KEYS = {
    "home_score",
    "away_score",
    "total_runs",
    "home_win",
    "away_win",
    "game_status",
    "gameStatusText",
}

MARKET_ALIASES = {
    "moneyline": "moneyline",
    "h2h": "moneyline",
    "pointspread": "run_line",
    "point_spread": "run_line",
    "spread": "run_line",
    "spreads": "run_line",
    "runline": "run_line",
    "run_line": "run_line",
    "totals": "game_total_runs",
    "total": "game_total_runs",
    "game_total": "game_total_runs",
    "game_total_runs": "game_total_runs",
}

TEAM_ALIASES = {
    "ARI": "ARI",
    "AZ": "ARI",
    "ARIZONA": "ARI",
    "ARIZONA DIAMONDBACKS": "ARI",
    "DIAMONDBACKS": "ARI",
    "ATL": "ATL",
    "ATLANTA": "ATL",
    "ATLANTA BRAVES": "ATL",
    "BRAVES": "ATL",
    "BAL": "BAL",
    "BALTIMORE": "BAL",
    "BALTIMORE ORIOLES": "BAL",
    "ORIOLES": "BAL",
    "BOS": "BOS",
    "BOSTON": "BOS",
    "BOSTON RED SOX": "BOS",
    "RED SOX": "BOS",
    "CHC": "CHC",
    "CHICAGO CUBS": "CHC",
    "CUBS": "CHC",
    "CHW": "CHW",
    "CWS": "CHW",
    "CHICAGO WHITE SOX": "CHW",
    "WHITE SOX": "CHW",
    "CIN": "CIN",
    "CINCINNATI": "CIN",
    "CINCINNATI REDS": "CIN",
    "REDS": "CIN",
    "CLE": "CLE",
    "CLEVELAND": "CLE",
    "CLEVELAND GUARDIANS": "CLE",
    "CLEVELAND INDIANS": "CLE",
    "GUARDIANS": "CLE",
    "INDIANS": "CLE",
    "COL": "COL",
    "COLORADO": "COL",
    "COLORADO ROCKIES": "COL",
    "ROCKIES": "COL",
    "DET": "DET",
    "DETROIT": "DET",
    "DETROIT TIGERS": "DET",
    "TIGERS": "DET",
    "HOU": "HOU",
    "HOUSTON": "HOU",
    "HOUSTON ASTROS": "HOU",
    "ASTROS": "HOU",
    "KC": "KCR",
    "KCR": "KCR",
    "KANSAS CITY": "KCR",
    "KANSAS CITY ROYALS": "KCR",
    "ROYALS": "KCR",
    "LAA": "LAA",
    "ANA": "LAA",
    "LOS ANGELES ANGELS": "LAA",
    "LA ANGELS": "LAA",
    "ANGELS": "LAA",
    "LAD": "LAD",
    "LOS ANGELES DODGERS": "LAD",
    "LA DODGERS": "LAD",
    "DODGERS": "LAD",
    "MIA": "MIA",
    "MIAMI": "MIA",
    "MIAMI MARLINS": "MIA",
    "MARLINS": "MIA",
    "MIL": "MIL",
    "MILWAUKEE": "MIL",
    "MILWAUKEE BREWERS": "MIL",
    "BREWERS": "MIL",
    "MIN": "MIN",
    "MINNESOTA": "MIN",
    "MINNESOTA TWINS": "MIN",
    "TWINS": "MIN",
    "NYM": "NYM",
    "NEW YORK METS": "NYM",
    "NY METS": "NYM",
    "METS": "NYM",
    "NYY": "NYY",
    "NEW YORK YANKEES": "NYY",
    "NY YANKEES": "NYY",
    "YANKEES": "NYY",
    "OAK": "ATH",
    "ATH": "ATH",
    "OAKLAND": "ATH",
    "OAKLAND ATHLETICS": "ATH",
    "ATHLETICS": "ATH",
    "PHI": "PHI",
    "PHILADELPHIA": "PHI",
    "PHILADELPHIA PHILLIES": "PHI",
    "PHILLIES": "PHI",
    "PIT": "PIT",
    "PITTSBURGH": "PIT",
    "PITTSBURGH PIRATES": "PIT",
    "PIRATES": "PIT",
    "SD": "SDP",
    "SDP": "SDP",
    "SAN DIEGO": "SDP",
    "SAN DIEGO PADRES": "SDP",
    "PADRES": "SDP",
    "SEA": "SEA",
    "SEATTLE": "SEA",
    "SEATTLE MARINERS": "SEA",
    "MARINERS": "SEA",
    "SF": "SFG",
    "SFG": "SFG",
    "SAN FRANCISCO": "SFG",
    "SAN FRANCISCO GIANTS": "SFG",
    "GIANTS": "SFG",
    "STL": "STL",
    "ST. LOUIS": "STL",
    "ST LOUIS": "STL",
    "ST. LOUIS CARDINALS": "STL",
    "ST LOUIS CARDINALS": "STL",
    "CARDINALS": "STL",
    "TB": "TBR",
    "TBR": "TBR",
    "TAMPA BAY": "TBR",
    "TAMPA BAY RAYS": "TBR",
    "RAYS": "TBR",
    "TEX": "TEX",
    "TEXAS": "TEX",
    "TEXAS RANGERS": "TEX",
    "RANGERS": "TEX",
    "TOR": "TOR",
    "TORONTO": "TOR",
    "TORONTO BLUE JAYS": "TOR",
    "BLUE JAYS": "TOR",
    "WSH": "WSN",
    "WSN": "WSN",
    "WAS": "WSN",
    "WASHINGTON": "WSN",
    "WASHINGTON NATIONALS": "WSN",
    "NATIONALS": "WSN",
}


@dataclass(slots=True)
class ParsedHistoricalGameOdds:
    games_read: int = 0
    games: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    features: list[dict[str, Any]] = field(default_factory=list)
    grades: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HistoricalGameOddsImportResult:
    import_id: str
    source_file: str
    started_at: str
    finished_at: str
    status: str
    games_read: int = 0
    games_imported: int = 0
    line_rows_imported: int = 0
    feature_rows_written: int = 0
    grade_rows_written: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    csv_exports: dict[str, str] = field(default_factory=dict)
    http_status: int = 200

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.status == "success" else "error",
            "importStatus": self.status,
            "importId": self.import_id,
            "sourceFile": self.source_file,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "gamesRead": self.games_read,
            "gamesImported": self.games_imported,
            "lineRowsImported": self.line_rows_imported,
            "featureRowsWritten": self.feature_rows_written,
            "gradeRowsWritten": self.grade_rows_written,
            "warnings": self.warnings,
            "errors": self.errors,
            "csvExports": self.csv_exports,
            "_status": self.http_status,
        }

    def manifest(self) -> dict[str, Any]:
        return {
            "import_id": self.import_id,
            "source_file": self.source_file,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "games_read": self.games_read,
            "games_imported": self.games_imported,
            "line_rows_imported": self.line_rows_imported,
            "feature_rows_written": self.feature_rows_written,
            "grade_rows_written": self.grade_rows_written,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class HistoricalGameOddsImportService:
    """Import date-keyed historical MLB game odds into the warehouse."""

    def __init__(
        self,
        repository: HistoricalGameOddsRepository,
        *,
        settings: Settings = default_settings,
        grading_service: GameMarketGradingService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.grading_service = grading_service or GameMarketGradingService()

    @property
    def default_source_path(self) -> Path:
        return self.settings.data_dir / DEFAULT_SOURCE_RELATIVE_PATH

    def import_file(
        self,
        *,
        source_file: str | Path | None = None,
        export_csv: bool = False,
        initialize_schema: bool = True,
    ) -> HistoricalGameOddsImportResult:
        source_path = Path(source_file).resolve() if source_file else self.default_source_path.resolve()
        started_at = utc_now_text()
        import_id = stable_id("historical_game_odds_import", _display_path(source_path, self.settings.data_dir), started_at)
        source_display = _display_path(source_path, self.settings.data_dir)
        result = HistoricalGameOddsImportResult(
            import_id=import_id,
            source_file=source_display,
            started_at=started_at,
            finished_at="",
            status="running",
        )
        try:
            if initialize_schema:
                self.repository.initialize_schema()
            self.repository.upsert_import_manifest(result.manifest())
            if not source_path.exists():
                result.status = "failed"
                result.finished_at = utc_now_text()
                result.errors.append(f"Source file not found: {source_display}")
                result.http_status = 404
                self.repository.upsert_import_manifest(result.manifest())
                return result

            payload = json.loads(source_path.read_text(encoding="utf-8"))
            parsed = self.parse_payload(payload)
            result.games_read = parsed.games_read
            result.warnings.extend(parsed.warnings)

            result.games_imported = self.repository.upsert_games(parsed.games)
            result.line_rows_imported = self.repository.upsert_lines(parsed.lines)
            result.feature_rows_written = self.repository.upsert_features(parsed.features)
            result.grade_rows_written = self.repository.upsert_grades(parsed.grades)
            result.status = "success"
            result.finished_at = utc_now_text()
            if export_csv:
                result.csv_exports = self.export_csv_snapshots(
                    games=parsed.games,
                    lines=parsed.lines,
                    features=parsed.features,
                    grades=parsed.grades,
                    manifest=result.manifest(),
                )
            self.repository.upsert_import_manifest(result.manifest())
            return result
        except Exception as error:
            result.status = "failed"
            result.finished_at = utc_now_text()
            result.errors.append(f"{type(error).__name__}: {error}")
            result.http_status = 500
            try:
                self.repository.upsert_import_manifest(result.manifest())
            except Exception:
                pass
            return result

    def parse_payload(self, payload: Any) -> ParsedHistoricalGameOdds:
        parsed = ParsedHistoricalGameOdds()
        if not isinstance(payload, dict):
            parsed.warnings.append("Historical game odds payload is not a date-keyed object.")
            return parsed
        for date_key in sorted(payload):
            games = payload.get(date_key)
            if not isinstance(games, list):
                parsed.warnings.append(f"Skipped {date_key}: expected a list of games.")
                continue
            for index, raw_game in enumerate(games):
                if not isinstance(raw_game, dict):
                    parsed.warnings.append(f"Skipped {date_key} game {index}: expected an object.")
                    continue
                parsed.games_read += 1
                game = normalize_game(raw_game, fallback_date=clean(date_key))
                if not game["game_id"]:
                    parsed.warnings.append(f"Skipped {date_key} game {index}: missing teams or game date.")
                    continue
                parsed.games.append(game)
                parsed.lines.extend(flatten_game_odds(raw_game, game))
        parsed.features = build_game_market_features(parsed.games, parsed.lines)
        parsed.grades = self.grading_service.grade_lines(games=parsed.games, lines=parsed.lines)
        return parsed

    def export_csv_snapshots(
        self,
        *,
        games: Sequence[Mapping[str, Any]],
        lines: Sequence[Mapping[str, Any]],
        features: Sequence[Mapping[str, Any]],
        grades: Sequence[Mapping[str, Any]],
        manifest: Mapping[str, Any],
    ) -> dict[str, str]:
        export_dir = self.settings.data_dir / DEFAULT_EXPORT_RELATIVE_DIR
        export_dir.mkdir(parents=True, exist_ok=True)
        exports = {
            "lines": export_dir / "game_odds_long.csv",
            "features": export_dir / "game_odds_features.csv",
            "grades": export_dir / "game_market_grades.csv",
            "manifest": export_dir / "import_manifest.json",
        }
        _write_csv(exports["lines"], lines)
        _write_csv(exports["features"], features)
        _write_csv(exports["grades"], grades)
        exports["manifest"].write_text(json.dumps(dict(manifest), indent=2, sort_keys=True), encoding="utf-8")
        return {key: _display_path(path, self.settings.data_dir) for key, path in exports.items()}


def normalize_game(raw_game: Mapping[str, Any], *, fallback_date: str = "") -> dict[str, Any]:
    game_view = raw_game.get("gameView") if isinstance(raw_game.get("gameView"), dict) else {}
    start_time_utc = normalize_start_time(game_view.get("startDate"))
    game_date = clean(fallback_date) or start_time_utc[:10]
    away_team = normalize_team(game_view.get("awayTeam"))
    home_team = normalize_team(game_view.get("homeTeam"))
    season = _season_from_date(game_date)
    game_id = stable_game_id(
        game_date=game_date,
        away_team=away_team,
        home_team=home_team,
        start_time_utc=start_time_utc,
    )
    now = utc_now_text()
    return {
        "game_id": game_id,
        "game_date": game_date,
        "season": season,
        "start_time_utc": start_time_utc,
        "game_type": clean(game_view.get("gameType")),
        "venue": clean(game_view.get("venueName")),
        "away_team": away_team,
        "home_team": home_team,
        "away_score": _optional_int(game_view.get("awayTeamScore")),
        "home_score": _optional_int(game_view.get("homeTeamScore")),
        "game_status": clean(game_view.get("gameStatusText")),
        "created_at": now,
        "updated_at": now,
    }


def flatten_game_odds(raw_game: Mapping[str, Any], game: Mapping[str, Any]) -> list[dict[str, Any]]:
    odds = raw_game.get("odds") if isinstance(raw_game.get("odds"), dict) else {}
    rows: list[dict[str, Any]] = []
    for source_market, entries in odds.items():
        market = normalize_market(source_market)
        if not market or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            rows.extend(_line_rows_for_entry(game=game, market=market, entry=entry))
    return rows


def build_game_market_features(
    games: Sequence[Mapping[str, Any]],
    lines: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    lines_by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in lines:
        lines_by_game[clean(raw.get("game_id"))].append(dict(raw))
    features: list[dict[str, Any]] = []
    now = utc_now_text()
    for game in games:
        game_id = clean(game.get("game_id"))
        game_lines = lines_by_game.get(game_id, [])
        moneyline_rows = [row for row in game_lines if row.get("market") == "moneyline"]
        total_rows = [row for row in game_lines if row.get("market") == "game_total_runs"]
        runline_rows = [row for row in game_lines if row.get("market") == "run_line"]

        open_total = _average(_unique_book_values(total_rows, side="over", field="opening_line"))
        current_total = _average(_unique_book_values(total_rows, side="over", field="current_line"))
        home_open_prob = _average(_side_values(moneyline_rows, "home", "opening_no_vig_prob"))
        away_open_prob = _average(_side_values(moneyline_rows, "away", "opening_no_vig_prob"))
        home_current_prob = _average(_side_values(moneyline_rows, "home", "current_no_vig_prob"))
        away_current_prob = _average(_side_values(moneyline_rows, "away", "current_no_vig_prob"))
        feature = {
            "game_id": game_id,
            "game_date": clean(game.get("game_date")),
            "season": _optional_int(game.get("season")) or _season_from_date(clean(game.get("game_date"))),
            "away_team": clean(game.get("away_team")).upper(),
            "home_team": clean(game.get("home_team")).upper(),
            "venue": clean(game.get("venue")),
            "consensus_open_total": open_total,
            "consensus_current_total": current_total,
            "total_line_movement": _difference(current_total, open_total),
            "home_open_moneyline_consensus": _average(_side_values(moneyline_rows, "home", "opening_odds")),
            "away_open_moneyline_consensus": _average(_side_values(moneyline_rows, "away", "opening_odds")),
            "home_current_moneyline_consensus": _average(_side_values(moneyline_rows, "home", "current_odds")),
            "away_current_moneyline_consensus": _average(_side_values(moneyline_rows, "away", "current_odds")),
            "home_no_vig_win_prob_open": home_open_prob,
            "away_no_vig_win_prob_open": away_open_prob,
            "home_no_vig_win_prob_current": home_current_prob,
            "away_no_vig_win_prob_current": away_current_prob,
            "favorite_team_open": _favorite_team(game, home_open_prob, away_open_prob),
            "favorite_team_current": _favorite_team(game, home_current_prob, away_current_prob),
            "book_count_moneyline": _book_count(moneyline_rows),
            "book_count_total": _book_count(total_rows),
            "book_count_runline": _book_count(runline_rows),
            "market_disagreement_score": market_disagreement_score(moneyline_rows, total_rows, runline_rows),
            "quality_flags": _feature_quality_flags(moneyline_rows, total_rows, runline_rows),
            "created_at": now,
            "updated_at": now,
        }
        _assert_no_leakage(feature)
        features.append(feature)
    return features


def stable_game_id(*, game_date: str, away_team: str, home_team: str, start_time_utc: str) -> str:
    if not clean(game_date) or not clean(away_team) or not clean(home_team):
        return ""
    return stable_id("historical_game", game_date, away_team.upper(), home_team.upper(), start_time_utc)


def normalize_team(value: Any) -> str:
    candidates: list[Any] = []
    if isinstance(value, dict):
        candidates.extend(
            [
                value.get("shortName"),
                value.get("abbreviation"),
                value.get("teamCode"),
                value.get("fullName"),
                value.get("displayName"),
                value.get("name"),
                value.get("nickname"),
            ]
        )
    else:
        candidates.append(value)
    for candidate in candidates:
        key = _team_key(candidate)
        if key in TEAM_ALIASES:
            return TEAM_ALIASES[key]
    fallback = _team_key(candidates[0] if candidates else "")
    return fallback[:4] if fallback else ""


def normalize_sportsbook(value: Any) -> str:
    text = clean(value).lower()
    if not text:
        return "unknown"
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "draft_kings": "draftkings",
        "dk": "draftkings",
        "fan_duel": "fanduel",
        "fd": "fanduel",
        "bet_365": "bet365",
        "william_hill": "caesars",
    }
    return aliases.get(text, text)


def normalize_market(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")
    return MARKET_ALIASES.get(text, "")


def normalize_start_time(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
        return parsed.isoformat().replace("+00:00", "Z")
    except ValueError:
        return text


def american_implied_probability(odds: Any) -> float | None:
    value = _optional_float(odds)
    if value is None or value == 0:
        return None
    if value > 0:
        return round(100.0 / (value + 100.0), 10)
    return round(abs(value) / (abs(value) + 100.0), 10)


def no_vig_probabilities(*probabilities: float | None) -> tuple[float | None, ...]:
    if not probabilities or any(prob is None for prob in probabilities):
        return tuple(None for _ in probabilities)
    total = sum(float(prob or 0) for prob in probabilities)
    if total <= 0:
        return tuple(None for _ in probabilities)
    return tuple(round(float(prob or 0) / total, 10) for prob in probabilities)


def market_disagreement_score(
    moneyline_rows: Sequence[Mapping[str, Any]],
    total_rows: Sequence[Mapping[str, Any]],
    runline_rows: Sequence[Mapping[str, Any]],
) -> float | None:
    components: list[float] = []
    home_probs = _side_values(moneyline_rows, "home", "current_no_vig_prob")
    if len(home_probs) >= 2:
        components.append((max(home_probs) - min(home_probs)) * 100.0)
    totals = _unique_book_values(total_rows, side="over", field="current_line")
    if len(totals) >= 2:
        components.append(max(totals) - min(totals))
    runlines = _unique_book_values(runline_rows, side="home", field="current_line")
    if len(runlines) >= 2:
        components.append(max(runlines) - min(runlines))
    if not components:
        return None
    return round(sum(components), 6)


def _line_rows_for_entry(*, game: Mapping[str, Any], market: str, entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    sportsbook = normalize_sportsbook(entry.get("sportsbook"))
    opening = entry.get("openingLine") if isinstance(entry.get("openingLine"), dict) else {}
    current = entry.get("currentLine") if isinstance(entry.get("currentLine"), dict) else {}
    if market == "moneyline":
        specs = (
            ("home", "homeOdds", ""),
            ("away", "awayOdds", ""),
        )
    elif market == "run_line":
        specs = (
            ("home", "homeOdds", "homeSpread"),
            ("away", "awayOdds", "awaySpread"),
        )
    elif market == "game_total_runs":
        specs = (
            ("over", "overOdds", "total"),
            ("under", "underOdds", "total"),
        )
    else:
        return []

    rows: list[dict[str, Any]] = []
    opening_probs: list[float | None] = []
    current_probs: list[float | None] = []
    for side, odds_key, line_key in specs:
        opening_odds = _optional_int(opening.get(odds_key))
        current_odds = _optional_int(current.get(odds_key))
        opening_line = _optional_float(opening.get(line_key)) if line_key else None
        current_line = _optional_float(current.get(line_key)) if line_key else None
        opening_prob = american_implied_probability(opening_odds)
        current_prob = american_implied_probability(current_odds)
        opening_probs.append(opening_prob)
        current_probs.append(current_prob)
        quality_flags = []
        if opening_odds is None:
            quality_flags.append("missing_opening_odds")
        if current_odds is None:
            quality_flags.append("missing_current_odds")
        if market in {"run_line", "game_total_runs"} and opening_line is None:
            quality_flags.append("missing_opening_line")
        if market in {"run_line", "game_total_runs"} and current_line is None:
            quality_flags.append("missing_current_line")
        game_id = clean(game.get("game_id"))
        now = utc_now_text()
        rows.append(
            {
                "id": stable_id("historical_game_line", game_id, sportsbook, market, side),
                "game_id": game_id,
                "game_date": clean(game.get("game_date")),
                "sportsbook": sportsbook,
                "market": market,
                "side": side,
                "opening_odds": opening_odds,
                "current_odds": current_odds,
                "opening_line": opening_line,
                "current_line": current_line,
                "opening_implied_prob": opening_prob,
                "current_implied_prob": current_prob,
                "opening_no_vig_prob": None,
                "current_no_vig_prob": None,
                "odds_movement": _difference(current_odds, opening_odds),
                "line_movement": _difference(current_line, opening_line),
                "quality_flags": quality_flags,
                "created_at": now,
                "updated_at": now,
            }
        )

    opening_no_vig = no_vig_probabilities(*opening_probs)
    current_no_vig = no_vig_probabilities(*current_probs)
    for index, row in enumerate(rows):
        row["opening_no_vig_prob"] = opening_no_vig[index]
        row["current_no_vig_prob"] = current_no_vig[index]
    return rows


def _feature_quality_flags(
    moneyline_rows: Sequence[Mapping[str, Any]],
    total_rows: Sequence[Mapping[str, Any]],
    runline_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    flags = []
    if not moneyline_rows:
        flags.append("missing_moneyline_market")
    if not total_rows:
        flags.append("missing_total_market")
    if not runline_rows:
        flags.append("missing_runline_market")
    return flags


def _favorite_team(game: Mapping[str, Any], home_prob: float | None, away_prob: float | None) -> str:
    if home_prob is None or away_prob is None or home_prob == away_prob:
        return ""
    return clean(game.get("home_team") if home_prob > away_prob else game.get("away_team")).upper()


def _side_values(rows: Sequence[Mapping[str, Any]], side: str, field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if clean(row.get("side")).lower() != side:
            continue
        value = _optional_float(row.get(field))
        if value is not None:
            values.append(value)
    return values


def _unique_book_values(rows: Sequence[Mapping[str, Any]], *, side: str, field: str) -> list[float]:
    values: dict[str, float] = {}
    for row in rows:
        if clean(row.get("side")).lower() != side:
            continue
        value = _optional_float(row.get(field))
        if value is not None:
            values[clean(row.get("sportsbook"))] = value
    return list(values.values())


def _book_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({clean(row.get("sportsbook")) for row in rows if clean(row.get("sportsbook"))})


def _average(values: Sequence[float | int]) -> float | None:
    clean_values = [float(value) for value in values if _optional_float(value) is not None]
    if not clean_values:
        return None
    return round(sum(clean_values) / len(clean_values), 6)


def _difference(current: Any, opening: Any) -> float | None:
    current_value = _optional_float(current)
    opening_value = _optional_float(opening)
    if current_value is None or opening_value is None:
        return None
    return round(current_value - opening_value, 6)


def _optional_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(str(value).replace("+", ""))
        if math.isnan(parsed):
            return None
        return int(parsed)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        parsed = float(str(value).replace("+", ""))
        if math.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _season_from_date(value: str) -> int:
    try:
        return int(clean(value)[:4])
    except ValueError:
        return 0


def _team_key(value: Any) -> str:
    text = clean(value).upper().replace(".", "")
    return re.sub(r"\s+", " ", text).strip()


def _assert_no_leakage(feature: Mapping[str, Any]) -> None:
    leaking = LEAKAGE_FORBIDDEN_FEATURE_KEYS.intersection(feature.keys())
    if leaking:
        raise ValueError(f"Pregame historical game features include label fields: {sorted(leaking)}")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json_text(value, [] if isinstance(value, list) else {})
    return value


def _display_path(path: Path, data_dir: Path) -> str:
    try:
        return str(Path("data") / path.resolve().relative_to(data_dir.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        return str(path).replace("\\", "/")
