from __future__ import annotations

import csv
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def norm_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    tokens = []
    token = ""
    for ch in text:
        if ch.isalnum():
            token += ch
        elif token:
            tokens.append(token)
            token = ""
    if token:
        tokens.append(token)
    while tokens and tokens[-1] in {"jr", "sr", "ii", "iii", "iv", "v"}:
        tokens.pop()
    leading: list[str] = []
    while tokens and len(tokens[0]) == 1:
        leading.append(tokens.pop(0))
    if leading:
        tokens.insert(0, "".join(leading) if len(leading) > 1 else leading[0] + (tokens.pop(0) if tokens else ""))
    return " ".join(tokens)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _game_pk(row: dict[str, str]) -> str:
    return clean(row.get("gamePk") or row.get("game_pk") or row.get("game_id"))


@dataclass(frozen=True)
class BridgeConfig:
    min_overlap: int = 8
    min_event_share: float = 0.30


class ActionNetworkEventBridgeService:
    def __init__(self, config: BridgeConfig | None = None) -> None:
        self.config = config or BridgeConfig()

    def build_rows(
        self,
        *,
        odds_rows: list[dict[str, str]],
        batter_rows: list[dict[str, str]],
        pitcher_rows: list[dict[str, str]],
        team_rows: list[dict[str, str]] | None = None,
        snapshot_id: str = "",
    ) -> list[dict[str, str]]:
        del team_rows
        local_games: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in [*batter_rows, *pitcher_rows]:
            game_date = clean(row.get("date") or row.get("game_date"))[:10]
            game_pk = _game_pk(row)
            player = norm_name(row.get("player") or row.get("player_name"))
            if game_date and game_pk and player:
                local_games[(game_date, game_pk)].add(player)

        events: dict[tuple[str, str], set[str]] = defaultdict(set)
        event_snapshot: dict[tuple[str, str], str] = {}
        for row in odds_rows:
            game_date = clean(row.get("game_date"))[:10]
            event_id = clean(row.get("event_id"))
            player = norm_name(row.get("player_name"))
            if game_date and event_id and player:
                key = (game_date, event_id)
                events[key].add(player)
                event_snapshot[key] = snapshot_id or clean(row.get("snapshot_id"))

        output: list[dict[str, str]] = []
        used_confirmed_games: dict[tuple[str, str], int] = defaultdict(int)
        pending: list[dict[str, str]] = []

        for (game_date, event_id), event_players in sorted(events.items()):
            candidates: list[tuple[int, float, float, str, set[str], int]] = []
            for (local_date, game_pk), local_players in local_games.items():
                if local_date != game_date:
                    continue
                overlap_set = event_players & local_players
                overlap = len(overlap_set)
                event_share = overlap / len(event_players) if event_players else 0.0
                game_share = overlap / len(local_players) if local_players else 0.0
                confidence = (event_share + game_share) / 2
                candidates.append((overlap, event_share, confidence, game_pk, overlap_set, len(local_players)))

            candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            best = candidates[0] if candidates else (0, 0.0, 0.0, "", set(), 0)
            second = candidates[1] if len(candidates) > 1 else None
            duplicate_best = bool(second and second[0] == best[0] and best[0] > 0)
            overlap, event_share, confidence, game_pk, overlap_set, local_count = best
            game_share = overlap / local_count if local_count else 0.0
            confirmed = (
                overlap >= self.config.min_overlap
                and event_share >= self.config.min_event_share
                and not duplicate_best
                and bool(game_pk)
            )
            reason = ""
            if not game_pk:
                reason = "missing_truth_logs"
            elif duplicate_best:
                reason = "duplicate_best_gamePk"
            elif overlap < self.config.min_overlap:
                reason = "low_overlap"
            elif event_share < self.config.min_event_share:
                reason = "low_event_share"

            row = {
                "source": "actionnetwork",
                "game_date": game_date,
                "snapshot_id": event_snapshot.get((game_date, event_id), ""),
                "event_id": event_id,
                "gamePk": game_pk,
                "event_players": str(len(event_players)),
                "local_players": str(local_count),
                "overlap": str(overlap),
                "event_share": f"{event_share:.6f}",
                "game_share": f"{game_share:.6f}",
                "confidence": f"{confidence:.6f}",
                "duplicate_best_gamePk": "1" if duplicate_best else "0",
                "bridge_status": "confirmed" if confirmed else "rejected",
                "exclude_from_ml": "0" if confirmed else "1",
                "exclude_reason": "" if confirmed else reason,
                "sample_overlap": "; ".join(sorted(overlap_set)[:8]),
            }
            pending.append(row)
            if confirmed:
                used_confirmed_games[(game_date, game_pk)] += 1

        for row in pending:
            if row["bridge_status"] == "confirmed" and used_confirmed_games[(row["game_date"], row["gamePk"])] > 1:
                row = dict(row)
                row["duplicate_best_gamePk"] = "1"
                row["bridge_status"] = "rejected"
                row["exclude_from_ml"] = "1"
                row["exclude_reason"] = "duplicate_gamePk_bridge"
            output.append(row)

        return output
