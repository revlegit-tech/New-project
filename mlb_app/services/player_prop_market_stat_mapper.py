from __future__ import annotations

from typing import Any

MARKET_STAT_KEYS: dict[str, str] = {
    "batter_hits": "hits",
    "batter_total_bases": "totalBases",
    "batter_home_runs": "homeRuns",
    "batter_rbis": "rbi",
    "batter_runs": "runs",
    "batter_walks": "baseOnBalls",
    "batter_singles": "singles",
    "batter_doubles": "doubles",
    "batter_stolen_bases": "stolenBases",
    "batter_2plus_hits": "hits",
    "batter_2plus_home_runs": "homeRuns",
    "batter_2plus_rbis": "rbi",
    "batter_3plus_rbis": "rbi",
    "pitcher_strikeouts": "strikeOuts",
    "pitcher_strikeouts_alt": "strikeOuts",
    "pitcher_outs": "outs",
    "pitcher_hits_allowed": "hitsAllowed",
    "pitcher_earned_runs": "earnedRuns",
}


def market_to_stat_key(market: str) -> str | None:
    text = _normalize_market(market)
    if text in MARKET_STAT_KEYS:
        return MARKET_STAT_KEYS[text]
    if text.endswith("_alt") and text[:-4] in MARKET_STAT_KEYS:
        return MARKET_STAT_KEYS[text[:-4]]
    return None


def is_supported_market(market: str) -> bool:
    return market_to_stat_key(market) is not None


def grade_over_under(actual_value: float, line: float, side: str) -> dict[str, Any]:
    actual = _float_or_none(actual_value)
    threshold = _float_or_none(line)
    normalized_side = normalize_side(side)
    if actual is None or threshold is None or normalized_side not in {"over", "under"}:
        return {
            "result": "ungraded",
            "hit": False,
            "push": False,
            "void": False,
            "label_status": "invalid_line",
            "label_reason": "Actual value, line, or side could not be graded.",
        }
    if actual == threshold:
        return {
            "result": "push",
            "hit": False,
            "push": True,
            "void": False,
            "label_status": "graded",
            "label_reason": "Actual value equaled the prop line.",
        }
    win = actual > threshold if normalized_side == "over" else actual < threshold
    return {
        "result": "win" if win else "loss",
        "hit": bool(win),
        "push": False,
        "void": False,
        "label_status": "graded",
        "label_reason": f"{normalized_side.title()} graded against actual value.",
    }


def normalize_side(side: str) -> str:
    text = str(side or "").strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    if text in {"o", "over", "more", "yes", "y", "hit", "true", "1"}:
        return "over"
    if text in {"u", "under", "less", "no", "n", "miss", "false", "0"}:
        return "under"
    if "over" in text:
        return "over"
    if "under" in text:
        return "under"
    if text in {"", "none", "null"}:
        return "over"
    return text


def _normalize_market(market: str) -> str:
    return str(market or "").strip().lower().replace("-", "_")


def _float_or_none(value: Any) -> float | None:
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None
