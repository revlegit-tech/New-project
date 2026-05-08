from pathlib import Path
import re

path = Path("app.py")
text = path.read_text(encoding="utf-8")

pattern = r'def playerboard_payload\(query: dict\[str, list\[str\]\]\) -> dict\[str, Any\]:.*?\n\ndef player_hit_rates_payload'

replacement = r'''
AUTO_PLAYERBOARD_REBUILD_COOLDOWN_SECONDS = 600
_AUTO_PLAYERBOARD_LAST_ATTEMPT: dict[tuple[int, str], float] = {}


def _query_flag_enabled(query: dict[str, list[str]], key: str, default: str = "1") -> bool:
    return query.get(key, [default])[0].strip().lower() not in {"0", "false", "no", "off"}


def _payload_player_prop_count(payload: dict[str, Any]) -> int:
    rows = payload.get("top") or []
    return sum(
        1
        for row in rows
        if str(row.get("market") or "").startswith(("batter_", "pitcher_"))
    )


def _auto_sync_player_props_for_date(season: int, date_label: str, limit: int) -> dict[str, Any]:
    """Best-effort automatic player-prop sync for UI requests.

    This keeps the Props UI populated without requiring a manual daily
    playerboard rebuild. It is intentionally throttled so repeated page loads
    do not hammer PropLine if markets are not available yet.
    """
    from playerboard import build_playerboard

    attempt_key = (int(season), str(date_label))
    now_ts = time.time()
    last_attempt = _AUTO_PLAYERBOARD_LAST_ATTEMPT.get(attempt_key, 0.0)

    if now_ts - last_attempt < AUTO_PLAYERBOARD_REBUILD_COOLDOWN_SECONDS:
        return {
            "attempted": False,
            "reason": "cooldown",
            "cooldownSeconds": AUTO_PLAYERBOARD_REBUILD_COOLDOWN_SECONDS,
        }

    _AUTO_PLAYERBOARD_LAST_ATTEMPT[attempt_key] = now_ts

    source_path = DATA_DIR / "odds" / f"propline_props_{date_label}.csv"
    sync_result: dict[str, Any] | None = None

    if not source_path.exists() or source_path.stat().st_size < 128:
        try:
            sync_result = propline_props_payload({
                "date": [date_label],
                "markets": [",".join(DAILY_WORKFLOW_MARKETS)],
                "save": ["1"],
            })
        except Exception as error:
            sync_result = {
                "error": str(error),
                "note": "PropLine auto-sync failed. Playerboard rebuild will use any existing saved source files.",
            }

    try:
        build_result = build_playerboard(
            season=season,
            date_label=date_label,
            market="",
            limit=max(int(limit or 0), 5000),
            save=True,
        )
    except Exception as error:
        return {
            "attempted": True,
            "sourcePath": str(source_path),
            "sync": sync_result,
            "buildError": str(error),
        }

    return {
        "attempted": True,
        "sourcePath": str(source_path),
        "sync": sync_result,
        "build": {
            "propsLoaded": build_result.get("propsLoaded"),
            "cardsBuilt": build_result.get("cardsBuilt"),
            "saved": build_result.get("saved"),
            "errors": build_result.get("errors", [])[:5],
        },
    }


def playerboard_payload(query: dict[str, list[str]]) -> dict[str, Any]:
    from playerboard import build_playerboard, load_saved_playerboard

    season = int(query.get("season", ["2026"])[0])
    date_label = query.get("date", [""])[0]
    market = query.get("market", [""])[0]
    limit = int(query.get("limit", ["50"])[0])

    # UI/API loads should not append ML snapshots by default.
    # GitHub collector calls build_playerboard(..., save=True) directly.
    save = query.get("save", ["0"])[0] in {"1", "true", "True", "yes"}
    refresh = query.get("refresh", ["0"])[0] in {"1", "true", "True", "yes"}
    build_if_missing = query.get("buildIfMissing", ["0"])[0] in {"1", "true", "True", "yes"}
    auto_player_props = _query_flag_enabled(query, "autoPlayerProps", "1")

    if not save and not refresh:
        cached = load_saved_playerboard(season=season, date_label=date_label, market=market, limit=limit)

        needs_auto_player_props = (
            auto_player_props
            and not market
            and bool(date_label)
            and _payload_player_prop_count(cached) == 0
        )

        if needs_auto_player_props:
            auto_result = _auto_sync_player_props_for_date(season, date_label, limit)
            refreshed = load_saved_playerboard(season=season, date_label=date_label, market=market, limit=limit)
            refreshed["autoPlayerProps"] = auto_result

            # Return the refreshed board whether or not the auto-sync succeeded.
            # If PropLine is unavailable, the UI still gets the existing saved board.
            return refreshed

        if cached.get("cacheHit") or not build_if_missing:
            return cached

    return build_playerboard(season=season, date_label=date_label, market=market, limit=limit, save=save)


def player_hit_rates_payload'''

new_text, count = re.subn(pattern, replacement, text, flags=re.S)

if count != 1:
    raise SystemExit(f"Patch failed. Expected 1 replacement, got {count}.")

backup = path.with_suffix(".py.before-auto-player-props")
backup.write_text(text, encoding="utf-8")
path.write_text(new_text, encoding="utf-8")

print("Patched app.py")
print(f"Backup saved to {backup}")
