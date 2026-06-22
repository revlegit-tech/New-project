from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.warehouse_db import WarehouseDatabase
from mlb_app.repositories.warehouse_utils import clean, first, json_text, parse_json_object, stable_id, utc_now_text


@dataclass(frozen=True)
class FeatureRepositoryResult:
    dataset: str
    count: int
    mode: str
    warnings: tuple[str, ...] = ()


class WarehouseFeatureRowRepository:
    """Small DB-first/CSV-fallback row store for feature warehouse datasets."""

    def __init__(
        self,
        db: WarehouseDatabase,
        *,
        table_name: str,
        csv_root: Path,
        allowed_datasets: set[str],
        id_prefix: str,
        settings: Settings = default_settings,
    ) -> None:
        self.db = db
        self.table_name = table_name
        self.csv_root = csv_root
        self.allowed_datasets = set(allowed_datasets)
        self.id_prefix = id_prefix
        self.settings = settings

    def upsert_rows(
        self,
        dataset: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        date_label: str = "",
        source_path: str | Path = "",
        replace_csv: bool = False,
    ) -> FeatureRepositoryResult:
        selected_dataset = self._dataset(dataset)
        values = [
            _feature_row(
                selected_dataset,
                row,
                date_label=date_label,
                source_path=source_path,
                id_prefix=self.id_prefix,
            )
            for row in rows
        ]
        if not values:
            return FeatureRepositoryResult(selected_dataset, 0, self._preferred_mode())

        if self.db.configured:
            try:
                count = self._upsert_db(values)
                return FeatureRepositoryResult(selected_dataset, count, "database")
            except Exception as error:
                if not self.db.fallback_to_csv:
                    raise
                warning = f"Warehouse DB write failed; used CSV fallback: {type(error).__name__}: {error}"
                count = self._upsert_csv(selected_dataset, values, replace=replace_csv)
                return FeatureRepositoryResult(selected_dataset, count, "csv_fallback", (warning,))

        count = self._upsert_csv(selected_dataset, values, replace=replace_csv)
        return FeatureRepositoryResult(selected_dataset, count, "csv")

    def read_rows(
        self,
        dataset: str,
        *,
        date_label: str = "",
        season: int | None = None,
        player_id: str = "",
        player_name: str = "",
        team: str = "",
        game_id: str = "",
    ) -> list[dict[str, Any]]:
        selected_dataset = self._dataset(dataset)
        rows: list[dict[str, Any]] = []
        if self.db.configured:
            try:
                rows = self._read_db(
                    selected_dataset,
                    date_label=date_label,
                    season=season,
                    player_id=player_id,
                    player_name=player_name,
                    team=team,
                    game_id=game_id,
                )
            except Exception:
                if not self.db.fallback_to_csv:
                    raise
            if rows or not self.db.fallback_to_csv:
                return rows
        return self._read_csv(
            selected_dataset,
            date_label=date_label,
            season=season,
            player_id=player_id,
            player_name=player_name,
            team=team,
            game_id=game_id,
        )

    def count_rows(self, dataset: str, *, date_label: str = "") -> int:
        return len(self.read_rows(dataset, date_label=date_label))

    def csv_path(self, dataset: str, *, date_label: str = "") -> Path:
        selected_dataset = self._dataset(dataset)
        suffix = f"_{date_label}" if clean(date_label) else ""
        return self.csv_root / f"{selected_dataset}{suffix}.csv"

    def _preferred_mode(self) -> str:
        return "database" if self.db.configured else "csv"

    def _dataset(self, dataset: str) -> str:
        selected = clean(dataset)
        if selected not in self.allowed_datasets:
            raise ValueError(f"Unsupported feature dataset: {selected or '<empty>'}")
        return selected

    def _upsert_db(self, values: Sequence[Mapping[str, Any]]) -> int:
        with self.db.session(write=True) as session:
            return session.executemany(
                f"""
                INSERT INTO {self.table_name}(
                  id, dataset, feature_date, season, game_id, player_id, player_name,
                  team, opponent, home_team, away_team, pitch_type, split, handedness,
                  source, source_path, row_json, created_at, updated_at
                ) VALUES (
                  :id, :dataset, :feature_date, :season, :game_id, :player_id, :player_name,
                  :team, :opponent, :home_team, :away_team, :pitch_type, :split, :handedness,
                  :source, :source_path, :row_json, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                  feature_date = excluded.feature_date,
                  season = excluded.season,
                  game_id = excluded.game_id,
                  player_id = excluded.player_id,
                  player_name = excluded.player_name,
                  team = excluded.team,
                  opponent = excluded.opponent,
                  home_team = excluded.home_team,
                  away_team = excluded.away_team,
                  pitch_type = excluded.pitch_type,
                  split = excluded.split,
                  handedness = excluded.handedness,
                  source = excluded.source,
                  source_path = excluded.source_path,
                  row_json = excluded.row_json,
                  updated_at = excluded.updated_at
                """,
                values,
            )

    def _read_db(
        self,
        dataset: str,
        *,
        date_label: str,
        season: int | None,
        player_id: str,
        player_name: str,
        team: str,
        game_id: str,
    ) -> list[dict[str, Any]]:
        clauses = ["dataset = :dataset"]
        params: dict[str, Any] = {"dataset": dataset}
        if date_label:
            clauses.append("feature_date = :feature_date")
            params["feature_date"] = date_label
        if season is not None:
            clauses.append("season = :season")
            params["season"] = int(season)
        if player_id:
            clauses.append("player_id = :player_id")
            params["player_id"] = player_id
        if player_name:
            clauses.append("player_name = :player_name")
            params["player_name"] = player_name
        if team:
            clauses.append("team = :team")
            params["team"] = team.upper()
        if game_id:
            clauses.append("game_id = :game_id")
            params["game_id"] = game_id
        with self.db.session() as session:
            rows = session.fetch_all(
                f"""
                SELECT * FROM {self.table_name}
                WHERE {' AND '.join(clauses)}
                ORDER BY feature_date ASC, player_name ASC, team ASC, game_id ASC
                """,
                params,
            )
        return [_payload_row(row) for row in rows]

    def _upsert_csv(self, dataset: str, values: Sequence[Mapping[str, Any]], *, replace: bool) -> int:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in values:
            date_value = clean(row.get("feature_date"))
            grouped.setdefault(date_value, []).append(_payload_row(row))
        written = 0
        for date_value, rows in grouped.items():
            path = self.csv_path(dataset, date_label=date_value)
            existing = [] if replace else _read_csv(path)
            merged = {clean(row.get("_warehouse_id")) or _csv_identity(dataset, row, self.id_prefix): row for row in existing}
            for row in rows:
                row.setdefault("_warehouse_id", _csv_identity(dataset, row, self.id_prefix))
                merged[clean(row.get("_warehouse_id"))] = row
            _write_csv(path, list(merged.values()))
            written += len(rows)
        return written

    def _read_csv(
        self,
        dataset: str,
        *,
        date_label: str,
        season: int | None,
        player_id: str,
        player_name: str,
        team: str,
        game_id: str,
    ) -> list[dict[str, Any]]:
        paths = [self.csv_path(dataset, date_label=date_label)] if date_label else sorted(self.csv_root.glob(f"{dataset}_*.csv"))
        rows: list[dict[str, Any]] = []
        for path in paths:
            rows.extend(_read_csv(path))
        return [
            row
            for row in rows
            if _matches(row, season=season, player_id=player_id, player_name=player_name, team=team, game_id=game_id)
        ]


def _feature_row(
    dataset: str,
    raw: Mapping[str, Any],
    *,
    date_label: str,
    source_path: str | Path,
    id_prefix: str,
) -> dict[str, Any]:
    row = dict(raw)
    feature_date = clean(first(row, "feature_date", "date", "game_date", "gameDate", "stat_date")) or clean(date_label)
    season = _optional_int(first(row, "season"))
    game_id = clean(first(row, "game_id", "gamePk", "game_pk", "mlb_game_id"))
    player_id = clean(first(row, "player_id", "mlbamId", "mlbam_id", "batter_id", "pitcher_id"))
    player_name = clean(first(row, "player_name", "player", "name", "batter", "pitcher"))
    team = clean(first(row, "team", "team_abbr", "teamAbbr", "batting_team", "pitching_team")).upper()
    opponent = clean(first(row, "opponent", "opponent_abbr", "opponentAbbr")).upper()
    pitch_type = clean(first(row, "pitch_type", "pitchType", "primary_pitch_type"))
    split = clean(first(row, "split", "split_key", "window", "home_away"))
    handedness = clean(first(row, "handedness", "stand", "p_throws", "throws"))
    row.setdefault("dataset", dataset)
    row.setdefault("feature_date", feature_date)
    row.setdefault("date", feature_date)
    row.setdefault("season", season or "")
    row.setdefault("game_id", game_id)
    row.setdefault("player_id", player_id)
    row.setdefault("player_name", player_name)
    row.setdefault("team", team)
    row.setdefault("opponent", opponent)
    row.setdefault("pitch_type", pitch_type)
    row.setdefault("split", split)
    row.setdefault("handedness", handedness)
    source = clean(first(row, "source", "provider")) or "local"
    source_path_text = clean(source_path) or clean(first(row, "source_path", "sourcePath"))
    now = utc_now_text()
    identity = _csv_identity(dataset, row, id_prefix)
    return {
        "id": identity,
        "dataset": dataset,
        "feature_date": feature_date,
        "season": season,
        "game_id": game_id,
        "player_id": player_id,
        "player_name": player_name,
        "team": team,
        "opponent": opponent,
        "home_team": clean(first(row, "home_team", "homeTeam")).upper(),
        "away_team": clean(first(row, "away_team", "awayTeam")).upper(),
        "pitch_type": pitch_type,
        "split": split,
        "handedness": handedness,
        "source": source,
        "source_path": source_path_text,
        "row_json": json_text(row, {}),
        "created_at": now,
        "updated_at": now,
    }


def _payload_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = parse_json_object(row.get("row_json"))
    payload.setdefault("dataset", clean(row.get("dataset")))
    payload.setdefault("feature_date", clean(row.get("feature_date")))
    payload.setdefault("date", clean(row.get("feature_date")))
    if row.get("season") not in {None, ""}:
        payload.setdefault("season", row.get("season"))
    for key in (
        "game_id",
        "player_id",
        "player_name",
        "team",
        "opponent",
        "home_team",
        "away_team",
        "pitch_type",
        "split",
        "handedness",
        "source",
        "source_path",
    ):
        value = clean(row.get(key))
        if value:
            payload.setdefault(key, value)
    payload.setdefault("_warehouse_id", clean(row.get("id")) or _csv_identity(clean(row.get("dataset")), payload, "feature_row"))
    return payload


def _csv_identity(dataset: str, row: Mapping[str, Any], id_prefix: str) -> str:
    explicit = clean(first(row, "_warehouse_id", "id", "row_id", "source_row_id"))
    if explicit:
        return explicit
    return stable_id(
        id_prefix,
        dataset,
        first(row, "feature_date", "date", "game_date"),
        first(row, "game_id", "gamePk", "game_pk"),
        first(row, "player_id", "mlbamId", "batter_id", "pitcher_id"),
        first(row, "player_name", "player", "batter", "pitcher"),
        first(row, "team"),
        first(row, "opponent"),
        first(row, "pitch_type"),
        first(row, "split"),
        first(row, "handedness"),
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _fieldnames(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    preferred = [
        "_warehouse_id",
        "dataset",
        "feature_date",
        "date",
        "season",
        "game_id",
        "player_id",
        "player_name",
        "team",
        "opponent",
        "home_team",
        "away_team",
        "pitch_type",
        "split",
        "handedness",
        "source",
        "source_path",
    ]
    observed: set[str] = set()
    for row in rows:
        observed.update(str(key) for key in row)
    return preferred + sorted(observed - set(preferred))


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json_text(value, [] if isinstance(value, list) else {})
    return str(value)


def _matches(
    row: Mapping[str, Any],
    *,
    season: int | None,
    player_id: str,
    player_name: str,
    team: str,
    game_id: str,
) -> bool:
    if season is not None and clean(row.get("season")) != str(int(season)):
        return False
    if player_id and clean(row.get("player_id")) != player_id:
        return False
    if player_name and clean(row.get("player_name")) != player_name:
        return False
    if team and clean(row.get("team")).upper() != team.upper():
        return False
    if game_id and clean(row.get("game_id")) != game_id:
        return False
    return True


def _optional_int(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
