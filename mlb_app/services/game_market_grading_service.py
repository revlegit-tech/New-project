from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mlb_app.repositories.warehouse_utils import clean, stable_id, utc_now_text


class GameMarketGradingService:
    """Grade historical game markets from final scores."""

    def grade_lines(
        self,
        *,
        games: Sequence[Mapping[str, Any]],
        lines: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        games_by_id = {clean(game.get("game_id")): dict(game) for game in games if clean(game.get("game_id"))}
        grades: list[dict[str, Any]] = []
        for raw_line in lines:
            line = dict(raw_line)
            game = games_by_id.get(clean(line.get("game_id")))
            if not game:
                continue
            grade = self.grade_line(game=game, line=line)
            if grade is not None:
                grades.append(grade)
        return grades

    def grade_line(self, *, game: Mapping[str, Any], line: Mapping[str, Any]) -> dict[str, Any] | None:
        away_score = _optional_int(game.get("away_score"))
        home_score = _optional_int(game.get("home_score"))
        if away_score is None or home_score is None:
            return None

        market = clean(line.get("market"))
        side = clean(line.get("side")).lower()
        selected_line = _coalesce_float(line.get("current_line"), line.get("opening_line"))
        selected_odds = _coalesce_int(line.get("current_odds"), line.get("opening_odds"))
        if selected_odds is None:
            return None

        result = ""
        push = False
        if market == "moneyline":
            if home_score == away_score:
                result = "push"
                push = True
            elif side == "home":
                result = "win" if home_score > away_score else "loss"
            elif side == "away":
                result = "win" if away_score > home_score else "loss"
        elif market == "run_line":
            if selected_line is None:
                return None
            if side == "home":
                score_with_spread = home_score + selected_line
                opponent_score = away_score
            elif side == "away":
                score_with_spread = away_score + selected_line
                opponent_score = home_score
            else:
                return None
            if score_with_spread == opponent_score:
                result = "push"
                push = True
            else:
                result = "win" if score_with_spread > opponent_score else "loss"
        elif market == "game_total_runs":
            if selected_line is None:
                return None
            total_runs = home_score + away_score
            if total_runs == selected_line:
                result = "push"
                push = True
            elif side == "over":
                result = "win" if total_runs > selected_line else "loss"
            elif side == "under":
                result = "win" if total_runs < selected_line else "loss"
            else:
                return None
        else:
            return None

        if not result:
            return None
        game_id = clean(line.get("game_id"))
        line_value = selected_line
        odds_value = selected_odds
        return {
            "id": stable_id("game_market_grade", game_id, line.get("sportsbook"), market, side),
            "game_id": game_id,
            "game_date": clean(line.get("game_date")) or clean(game.get("game_date")),
            "sportsbook": clean(line.get("sportsbook")),
            "market": market,
            "side": side,
            "line": line_value,
            "odds": odds_value,
            "result": result,
            "push_flag": push,
            "profit_1u": profit_1u(result=result, odds=odds_value),
            "closing_line_value": closing_line_value(line),
            "graded_at": utc_now_text(),
        }


def profit_1u(*, result: str, odds: int | float | None) -> float | None:
    normalized = clean(result).lower()
    if normalized == "push":
        return 0.0
    if normalized == "loss":
        return -1.0
    if normalized != "win":
        return None
    value = _coalesce_int(odds)
    if value is None or value == 0:
        return None
    if value > 0:
        return round(value / 100.0, 6)
    return round(100.0 / abs(value), 6)


def closing_line_value(line: Mapping[str, Any]) -> float | None:
    market = clean(line.get("market"))
    line_movement = _optional_float(line.get("line_movement"))
    odds_movement = _optional_float(line.get("odds_movement"))
    if market == "moneyline":
        return odds_movement
    if line_movement is not None:
        return line_movement
    return odds_movement


def _coalesce_int(*values: Any) -> int | None:
    for value in values:
        parsed = _optional_int(value)
        if parsed is not None:
            return parsed
    return None


def _coalesce_float(*values: Any) -> float | None:
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None


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
