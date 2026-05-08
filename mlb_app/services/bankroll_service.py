from __future__ import annotations

from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.json_store import JsonStore
from mlb_app.schemas.picks import BankrollSettings, STAKING_METHODS


class BankrollService:
    """User bankroll/risk settings with conservative defaults."""

    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.store = JsonStore(self.settings.data_dir / "user" / "bankroll_settings.json", default={"settings": BankrollSettings().to_api()})

    def payload(self) -> dict[str, Any]:
        settings = self.get_settings()
        return {
            "status": "ok",
            "settings": settings.to_api(),
            "allowedStakingMethods": list(STAKING_METHODS),
            "policy": {
                "defaultMode": "conservative",
                "message": "Stake sizing is capped by default. Research-only picks should stay at 0u until manually placed.",
            },
        }

    def get_settings(self) -> BankrollSettings:
        payload = self.store.read()
        return BankrollSettings.from_payload(payload.get("settings") if isinstance(payload, dict) else {})

    def update(self, body: dict[str, Any]) -> dict[str, Any]:
        settings = BankrollSettings.from_payload(body)
        self.store.write({"settings": settings.to_api()})
        return self.payload()

    def cap_stake_units(self, requested_units: float | None, *, research_only: bool = False) -> float:
        settings = self.get_settings()
        if research_only:
            return 0.0
        if requested_units is None:
            requested_units = min(0.25, settings.max_units_per_bet)
        return round(max(0.0, min(float(requested_units), settings.max_units_per_bet)), 2)

    def stake_amount(self, stake_units: float) -> float:
        return round(max(0.0, stake_units) * self.get_settings().default_unit_size, 2)
