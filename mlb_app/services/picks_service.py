from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.json_store import JsonStore
from mlb_app.schemas.picks import ACTIVE_PICK_STATUSES, PICK_STATUSES, BankrollSettings, Pick, game_key
from mlb_app.services.bankroll_service import BankrollService

PICKS_VERSION = "2026-05-my-picks-v1"


class PicksService:
    """Separates user-tracked picks from model suggestions/backtests."""

    def __init__(self, runtime_settings: Settings | None = None, *, bankroll_service: BankrollService | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.bankroll_service = bankroll_service or BankrollService(self.settings)
        self.store = JsonStore(self.settings.data_dir / "user" / "my_picks.json", default={"version": PICKS_VERSION, "picks": []})

    def payload(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        picks = self._filter_picks(self._read_picks(), query)
        settings = self.bankroll_service.get_settings()
        return {
            "status": "ok",
            "version": PICKS_VERSION,
            "picks": [pick.to_api() for pick in picks],
            "pickCount": len(picks),
            "settings": settings.to_api(),
            "exposure": self.exposure(picks=picks, settings=settings),
            "lifecycle": list(PICK_STATUSES),
            "policy": {
                "separateFromModelBacktests": True,
                "message": "These are user-tracked picks only. They do not alter model backtests or market readiness gates.",
            },
        }

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        settings = self.bankroll_service.get_settings()
        research_only = _is_research_only(body)
        stake_units = self.bankroll_service.cap_stake_units(_optional_float(body.get("stakeUnits") or body.get("stake_units")), research_only=research_only)
        base = dict(body)
        base.update(
            {
                "id": body.get("id") or _pick_id(body, now),
                "createdAt": now,
                "updatedAt": now,
                "status": body.get("status") or ("Watching" if stake_units <= 0 else "Placed"),
                "stakeUnits": stake_units,
                "stakeAmount": self.bankroll_service.stake_amount(stake_units),
                "warnings": _pick_warnings(body, stake_units=stake_units, settings=settings),
            }
        )
        pick = Pick.from_api(base)

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            rows = [row for row in _payload_picks(payload) if row.get("id") != pick.id]
            rows.append(pick.to_api())
            rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
            return {"version": PICKS_VERSION, "picks": rows}

        self.store.update(mutate)
        return {"status": "ok", "pick": pick.to_api(), "exposure": self.exposure()}

    def update(self, body: dict[str, Any]) -> dict[str, Any]:
        pick_id = str(body.get("id") or "").strip()
        if not pick_id:
            return {"status": "error", "code": "missing_pick_id", "error": "Pick id is required", "_status": 400}
        now = _now()
        updated_pick: Pick | None = None

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated_pick
            rows = _payload_picks(payload)
            next_rows: list[dict[str, Any]] = []
            found = False
            for row in rows:
                if row.get("id") != pick_id:
                    next_rows.append(row)
                    continue
                found = True
                merged = dict(row)
                for key, value in body.items():
                    if key != "id" and value is not None:
                        merged[key] = value
                if merged.get("status") not in PICK_STATUSES:
                    merged["status"] = row.get("status") or "Watching"
                stake_units = self.bankroll_service.cap_stake_units(_optional_float(merged.get("stakeUnits")), research_only=False)
                merged["stakeUnits"] = stake_units
                merged["stakeAmount"] = self.bankroll_service.stake_amount(stake_units)
                merged["updatedAt"] = now
                updated_pick = Pick.from_api(merged)
                next_rows.append(updated_pick.to_api())
            if not found:
                raise KeyError(pick_id)
            next_rows.sort(key=lambda row: str(row.get("createdAt") or ""), reverse=True)
            return {"version": PICKS_VERSION, "picks": next_rows}

        try:
            self.store.update(mutate)
        except KeyError:
            return {"status": "error", "code": "pick_not_found", "error": "Pick not found", "_status": 404}
        return {"status": "ok", "pick": updated_pick.to_api() if updated_pick else {}, "exposure": self.exposure()}

    def exposure(self, picks: list[Pick] | None = None, settings: BankrollSettings | None = None) -> dict[str, Any]:
        settings = settings or self.bankroll_service.get_settings()
        picks = picks if picks is not None else self._read_picks()
        active = [pick for pick in picks if pick.status in ACTIVE_PICK_STATUSES]
        by_game: dict[str, float] = {}
        by_player: dict[str, float] = {}
        by_market: dict[str, float] = {}
        warnings: list[str] = []
        for pick in active:
            units = max(0.0, float(pick.stake_units or 0.0))
            by_game[game_key(pick.team, pick.opponent)] = round(by_game.get(game_key(pick.team, pick.opponent), 0.0) + units, 2)
            by_player[pick.player or "Unknown player"] = round(by_player.get(pick.player or "Unknown player", 0.0) + units, 2)
            by_market[pick.market or "unknown_market"] = round(by_market.get(pick.market or "unknown_market", 0.0) + units, 2)
            if units > settings.max_units_per_bet:
                warnings.append(f"{pick.player or pick.market} exceeds max units per bet.")
            if _is_research_label(pick.readiness_label) and units > 0:
                warnings.append(f"{pick.player or pick.market} is research-only but has stake exposure.")
        if len(active) > settings.max_bets_per_slate:
            warnings.append(f"Active picks exceed max bets per slate ({settings.max_bets_per_slate}).")
        for game, units in by_game.items():
            if units > settings.max_exposure_per_game_units:
                warnings.append(f"Game exposure cap exceeded for {game}: {units:.2f}u.")
        for player, units in by_player.items():
            if units > settings.max_exposure_per_player_units:
                warnings.append(f"Player exposure cap exceeded for {player}: {units:.2f}u.")
        total_units = round(sum(max(0.0, float(pick.stake_units or 0.0)) for pick in active), 2)
        settled = [pick for pick in picks if pick.status in {"Won", "Lost", "Pushed", "Void", "Cashout"}]
        profit_units = round(sum(float(pick.profit_units or 0.0) for pick in settled), 2)
        return {
            "activePickCount": len(active),
            "totalStakeUnits": total_units,
            "totalStakeAmount": round(total_units * settings.default_unit_size, 2),
            "byGameUnits": _sorted_exposure(by_game),
            "byPlayerUnits": _sorted_exposure(by_player),
            "byMarketUnits": _sorted_exposure(by_market),
            "settledPickCount": len(settled),
            "profitUnits": profit_units,
            "profitAmount": round(profit_units * settings.default_unit_size, 2),
            "warnings": _dedupe(warnings),
            "caps": {
                "maxUnitsPerBet": settings.max_units_per_bet,
                "maxBetsPerSlate": settings.max_bets_per_slate,
                "maxExposurePerGameUnits": settings.max_exposure_per_game_units,
                "maxExposurePerPlayerUnits": settings.max_exposure_per_player_units,
            },
        }

    def _read_picks(self) -> list[Pick]:
        return [Pick.from_api(row) for row in _payload_picks(self.store.read())]

    @staticmethod
    def _filter_picks(picks: list[Pick], query: dict[str, list[str]]) -> list[Pick]:
        status = str((query.get("status") or [""])[0] or "")
        date = str((query.get("date") or [""])[0] or "")
        if status:
            picks = [pick for pick in picks if pick.status.lower() == status.lower()]
        if date:
            picks = [pick for pick in picks if pick.date == date]
        return picks


def _payload_picks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("picks", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _pick_id(body: dict[str, Any], now: str) -> str:
    raw = "|".join(str(body.get(key) or "") for key in ("date", "player", "team", "opponent", "market", "line", "americanOdds", "book")) + f"|{now}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_research_label(label: str) -> bool:
    return any(token in str(label or "").lower() for token in ("research", "not", "missing", "disabled", "no model"))


def _is_research_only(body: dict[str, Any]) -> bool:
    return "no bet" in str(body.get("decisionLabel") or "").lower() or "research" in str(body.get("suggestedStake") or "").lower() or _is_research_label(str(body.get("readinessLabel") or ""))


def _pick_warnings(body: dict[str, Any], *, stake_units: float, settings: BankrollSettings) -> list[str]:
    warnings: list[str] = []
    if stake_units <= 0:
        warnings.append("Saved as watchlist/research with 0u exposure.")
    if stake_units > settings.max_units_per_bet:
        warnings.append("Requested stake exceeded the max per-bet cap and was reduced.")
    if _is_research_only(body) and stake_units > 0:
        warnings.append("Research-only market should not carry stake exposure.")
    if not str(body.get("latestGradedDate") or "").strip():
        warnings.append("No latest fully graded slate is attached to this pick.")
    return _dedupe(warnings)


def _sorted_exposure(values: dict[str, float]) -> list[dict[str, Any]]:
    return [{"key": key, "units": units} for key, units in sorted(values.items(), key=lambda item: (-item[1], item[0])) if units > 0]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
