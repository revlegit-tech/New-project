from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ActionNetworkCollectionPolicy:
    game_date: str
    yyyymmdd: str
    collection_mode: str
    exclude_from_ml: str
    exclude_reason: str
    warning: str = ""


def normalize_actionnetwork_date(value: str | None, *, today: date | None = None) -> tuple[str, str, date]:
    today = today or date.today()
    if not value:
        return today.isoformat(), today.strftime("%Y%m%d"), today

    text = value.strip()
    if len(text) == 8 and text.isdigit():
        parsed = datetime.strptime(text, "%Y%m%d").date()
        return parsed.isoformat(), text, parsed
    if len(text) == 10:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
        return parsed.isoformat(), parsed.strftime("%Y%m%d"), parsed
    raise ValueError("Date must be YYYY-MM-DD or YYYYMMDD.")


def resolve_collection_policy(
    value: str | None,
    *,
    allow_past_diagnostic: bool = False,
    today: date | None = None,
) -> ActionNetworkCollectionPolicy:
    today = today or date.today()
    game_date, yyyymmdd, parsed = normalize_actionnetwork_date(value, today=today)

    if parsed < today and not allow_past_diagnostic:
        raise ValueError(
            "ActionNetwork is forward-only for ML. Past dates require "
            "--allow-past-diagnostic and will be excluded from ML."
        )

    if parsed < today:
        return ActionNetworkCollectionPolicy(
            game_date=game_date,
            yyyymmdd=yyyymmdd,
            collection_mode="diagnostic_past",
            exclude_from_ml="1",
            exclude_reason="actionnetwork_past_diagnostic",
            warning=(
                "WARNING: collecting a past ActionNetwork date as diagnostic_past. "
                "Rows are excluded from ML and must not become trainable."
            ),
        )

    return ActionNetworkCollectionPolicy(
        game_date=game_date,
        yyyymmdd=yyyymmdd,
        collection_mode="live_forward",
        exclude_from_ml="0",
        exclude_reason="",
    )
