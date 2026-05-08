from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PickStatus = Literal["Watching", "Placed", "Void", "Won", "Lost", "Pushed", "Cashout"]
StakeMethod = Literal["flat", "half_kelly", "quarter_kelly", "capped_kelly"]

PICK_STATUSES: tuple[str, ...] = ("Watching", "Placed", "Void", "Won", "Lost", "Pushed", "Cashout")
ACTIVE_PICK_STATUSES: tuple[str, ...] = ("Watching", "Placed")
STAKING_METHODS: tuple[str, ...] = ("flat", "half_kelly", "quarter_kelly", "capped_kelly")


@dataclass(frozen=True)
class BankrollSettings:
    bankroll: float = 1000.0
    default_unit_size: float = 10.0
    max_units_per_bet: float = 0.5
    max_bets_per_slate: int = 12
    max_exposure_per_game_units: float = 1.5
    max_exposure_per_player_units: float = 0.75
    staking_method: StakeMethod = "flat"
    conservative_mode: bool = True

    def to_api(self) -> dict[str, Any]:
        return {
            "bankroll": round(self.bankroll, 2),
            "defaultUnitSize": round(self.default_unit_size, 2),
            "maxUnitsPerBet": round(self.max_units_per_bet, 2),
            "maxBetsPerSlate": self.max_bets_per_slate,
            "maxExposurePerGameUnits": round(self.max_exposure_per_game_units, 2),
            "maxExposurePerPlayerUnits": round(self.max_exposure_per_player_units, 2),
            "stakingMethod": self.staking_method,
            "conservativeMode": self.conservative_mode,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "BankrollSettings":
        payload = payload or {}
        method = str(payload.get("stakingMethod") or payload.get("staking_method") or "flat")
        if method not in STAKING_METHODS:
            method = "flat"
        return cls(
            bankroll=max(0.0, _float(payload.get("bankroll"), 1000.0)),
            default_unit_size=max(0.01, _float(payload.get("defaultUnitSize") or payload.get("default_unit_size"), 10.0)),
            max_units_per_bet=max(0.0, _float(payload.get("maxUnitsPerBet") or payload.get("max_units_per_bet"), 0.5)),
            max_bets_per_slate=max(1, int(_float(payload.get("maxBetsPerSlate") or payload.get("max_bets_per_slate"), 12))),
            max_exposure_per_game_units=max(0.0, _float(payload.get("maxExposurePerGameUnits") or payload.get("max_exposure_per_game_units"), 1.5)),
            max_exposure_per_player_units=max(0.0, _float(payload.get("maxExposurePerPlayerUnits") or payload.get("max_exposure_per_player_units"), 0.75)),
            staking_method=method,  # type: ignore[arg-type]
            conservative_mode=_bool(payload.get("conservativeMode", payload.get("conservative_mode", True))),
        )


@dataclass(frozen=True)
class Pick:
    id: str
    created_at: str
    updated_at: str
    status: PickStatus = "Watching"
    source: str = "edge_board"
    date: str = ""
    player: str = ""
    team: str = ""
    opponent: str = ""
    market: str = ""
    market_display: str = ""
    side: str = "Over"
    line: str = ""
    american_odds: str = ""
    book: str = "Best available"
    stake_units: float = 0.0
    stake_amount: float = 0.0
    decision_label: str = "Watchlist"
    readiness_label: str = "Research only"
    confidence: str = "Research"
    model_probability_percent: str = ""
    implied_probability_percent: str = ""
    edge_percent: str = ""
    latest_graded_date: str = ""
    suggested_stake: str = "Research only"
    notes: str = ""
    profit_units: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_api(self) -> dict[str, Any]:
        payload = asdict(self)
        aliases = {
            "created_at": "createdAt",
            "updated_at": "updatedAt",
            "market_display": "marketDisplay",
            "american_odds": "americanOdds",
            "stake_units": "stakeUnits",
            "stake_amount": "stakeAmount",
            "decision_label": "decisionLabel",
            "readiness_label": "readinessLabel",
            "model_probability_percent": "modelProbabilityPercent",
            "implied_probability_percent": "impliedProbabilityPercent",
            "edge_percent": "edgePercent",
            "latest_graded_date": "latestGradedDate",
            "suggested_stake": "suggestedStake",
            "profit_units": "profitUnits",
        }
        for old, new in aliases.items():
            payload[new] = payload.pop(old)
        payload["gameKey"] = game_key(str(payload.get("team") or ""), str(payload.get("opponent") or ""))
        return payload

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Pick":
        status = str(payload.get("status") or "Watching")
        if status not in PICK_STATUSES:
            status = "Watching"
        return cls(
            id=str(payload.get("id") or ""),
            created_at=str(payload.get("createdAt") or payload.get("created_at") or ""),
            updated_at=str(payload.get("updatedAt") or payload.get("updated_at") or ""),
            status=status,  # type: ignore[arg-type]
            source=str(payload.get("source") or "edge_board"),
            date=str(payload.get("date") or ""),
            player=str(payload.get("player") or ""),
            team=str(payload.get("team") or ""),
            opponent=str(payload.get("opponent") or ""),
            market=str(payload.get("market") or ""),
            market_display=str(payload.get("marketDisplay") or payload.get("market_display") or ""),
            side=str(payload.get("side") or "Over"),
            line=str(payload.get("line") or ""),
            american_odds=str(payload.get("americanOdds") or payload.get("american_odds") or payload.get("odds") or ""),
            book=str(payload.get("book") or "Best available"),
            stake_units=_float(payload.get("stakeUnits") or payload.get("stake_units"), 0.0),
            stake_amount=_float(payload.get("stakeAmount") or payload.get("stake_amount"), 0.0),
            decision_label=str(payload.get("decisionLabel") or payload.get("decision_label") or "Watchlist"),
            readiness_label=str(payload.get("readinessLabel") or payload.get("readiness_label") or "Research only"),
            confidence=str(payload.get("confidence") or "Research"),
            model_probability_percent=str(payload.get("modelProbabilityPercent") or payload.get("model_probability_percent") or ""),
            implied_probability_percent=str(payload.get("impliedProbabilityPercent") or payload.get("implied_probability_percent") or ""),
            edge_percent=str(payload.get("edgePercent") or payload.get("edge_percent") or ""),
            latest_graded_date=str(payload.get("latestGradedDate") or payload.get("latest_graded_date") or ""),
            suggested_stake=str(payload.get("suggestedStake") or payload.get("suggested_stake") or "Research only"),
            notes=str(payload.get("notes") or ""),
            profit_units=_float(payload.get("profitUnits") or payload.get("profit_units"), 0.0),
            warnings=[str(item) for item in payload.get("warnings", []) if str(item).strip()] if isinstance(payload.get("warnings"), list) else [],
        )


def game_key(team: str, opponent: str) -> str:
    parts = sorted(part.strip().upper() for part in (team, opponent) if part and part.strip())
    return " @ ".join(parts) if parts else "Unknown game"


def _float(value: Any, fallback: float) -> float:
    try:
        if value in {None, ""}:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}
