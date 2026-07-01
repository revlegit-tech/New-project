from __future__ import annotations

import re
import unicodedata
from typing import Any

from mlb_app.services.player_prop_model_runtime import model_market_key
from mlb_app.services.team_match_utils import normalize_team_alias

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_PLAYER_DESCRIPTION_SUFFIXES = (
    "Strikeouts Thrown",
    "Pitcher Strikeouts",
    "Hits Allowed",
    "Earned Runs",
    "Stolen Bases",
    "Total Bases",
    "Home Runs",
    "Strikeouts",
    "Doubles",
    "Singles",
    "Walks",
    "RBIs",
    "Runs",
    "Hits",
)


def normalize_player_name(value: Any) -> str:
    """Return a deterministic player-name key without fuzzy matching."""

    text = str(value or "").strip()
    if not text:
        return ""
    text = _strip_descriptive_suffix(text)
    if "," in text:
        last, first = [part.strip() for part in text.split(",", 1)]
        if first.rstrip(".").casefold() in _SUFFIXES:
            text = last
        else:
            text = f"{first} {last}".strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("'", "").replace("`", "")
    text = re.sub(r"[^A-Za-z0-9]+", " ", text)
    parts = [part.casefold() for part in text.split() if part.strip()]
    while parts and parts[-1].rstrip(".").casefold() in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def normalize_pitcher_name(value: Any) -> str:
    return normalize_player_name(value)


def normalize_team(value: Any) -> str:
    return normalize_team_alias(value)


def normalize_opponent(value: Any) -> str:
    return normalize_team(value)


def normalize_book_key(value: Any) -> str:
    return _simple_key(value)


def normalize_market_key(value: Any) -> str:
    return model_market_key(value)


def _simple_key(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _strip_descriptive_suffix(value: str) -> str:
    side_match = re.search(r"\s+(?:Over|Under)\b", value, flags=re.IGNORECASE)
    if side_match:
        candidate = value[: side_match.start()].strip()
        if _looks_like_player_name(candidate):
            return candidate

    for suffix in _PLAYER_DESCRIPTION_SUFFIXES:
        pattern = rf"\s+(?:\d+(?:\.\d+)?\+?\s+)?{re.escape(suffix)}$"
        candidate = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if candidate != value and _looks_like_player_name(candidate):
            return candidate
    return value


def _looks_like_player_name(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z'.-]*", value)
    return len(tokens) >= 2
