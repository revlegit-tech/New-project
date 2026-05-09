from __future__ import annotations

import json
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.bankroll_repository import BankrollRepository
from mlb_app.schemas.picks import BankrollSettings, STAKING_METHODS


class BankrollService:
    """User bankroll/risk settings with conservative defaults."""

    def __init__(
        self,
        runtime_settings: Settings | None = None,
        *,
        repository: BankrollRepository | None = None,
        migrate_legacy_json: bool = True,
    ) -> None:
        self.settings = runtime_settings or default_settings
        self.repository = repository or BankrollRepository(self.settings)
        if migrate_legacy_json:
            self._migrate_legacy_json_if_needed()

    def payload(self) -> dict[str, Any]:
        settings = self.get_settings()
        return {
            "status": "ok",
            "settings": settings.to_api(),
            "allowedStakingMethods": list(STAKING_METHODS),
            "storage": {"sourceOfTruth": "sqlite", "path": str(self.repository.path)},
            "policy": {
                "defaultMode": "conservative",
                "message": "Stake sizing is capped by default. Research-only picks should stay at 0u until manually placed.",
            },
        }

    def get_settings(self) -> BankrollSettings:
        return self.repository.get_settings()

    def update(self, body: dict[str, Any]) -> dict[str, Any]:
        settings = BankrollSettings.from_payload(body)
        self.repository.save_settings(settings)
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

    def _migrate_legacy_json_if_needed(self) -> None:
        if self.repository.has_settings():
            return
        legacy_path = self.settings.data_dir / "user" / "bankroll_settings.json"
        if not legacy_path.exists():
            return
        try:
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        settings_payload = payload.get("settings") if isinstance(payload, dict) else None
        if isinstance(settings_payload, dict):
            self.repository.save_payload(settings_payload)
