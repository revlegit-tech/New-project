from __future__ import annotations

from pathlib import Path
from typing import Any

from mlb_app.config import Settings, settings as default_settings
from mlb_app.repositories.db import SQLiteDatabase, utc_now
from mlb_app.schemas.picks import BankrollSettings


class BankrollRepository:
    """SQLite-backed repository for user bankroll/risk settings."""

    def __init__(self, runtime_settings: Settings | None = None, *, db: SQLiteDatabase | None = None) -> None:
        self.settings = runtime_settings or default_settings
        self.db = db or SQLiteDatabase(self.settings.state_db_path)
        self.db.initialize()

    @property
    def path(self) -> Path:
        return self.db.path

    def has_settings(self) -> bool:
        row = self.db.fetch_one("SELECT 1 AS exists_flag FROM bankroll_settings WHERE id = 1")
        return row is not None

    def get_settings(self) -> BankrollSettings:
        row = self.db.fetch_one("SELECT * FROM bankroll_settings WHERE id = 1")
        if row is None:
            return BankrollSettings()
        return BankrollSettings.from_payload(_row_to_payload(row))

    def save_settings(self, settings: BankrollSettings) -> None:
        payload = settings.to_api()
        self.save_payload(payload)

    def save_payload(self, payload: dict[str, Any]) -> None:
        settings = BankrollSettings.from_payload(payload)
        with self.db.transaction() as connection:
            connection.execute(
                """
                INSERT INTO bankroll_settings(
                  id,
                  bankroll_amount,
                  unit_size,
                  max_daily_risk_units,
                  max_pick_risk_units,
                  max_bets_per_slate,
                  max_exposure_per_game_units,
                  max_exposure_per_player_units,
                  staking_method,
                  conservative_mode,
                  updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  bankroll_amount = excluded.bankroll_amount,
                  unit_size = excluded.unit_size,
                  max_daily_risk_units = excluded.max_daily_risk_units,
                  max_pick_risk_units = excluded.max_pick_risk_units,
                  max_bets_per_slate = excluded.max_bets_per_slate,
                  max_exposure_per_game_units = excluded.max_exposure_per_game_units,
                  max_exposure_per_player_units = excluded.max_exposure_per_player_units,
                  staking_method = excluded.staking_method,
                  conservative_mode = excluded.conservative_mode,
                  updated_at = excluded.updated_at
                """,
                (
                    settings.bankroll,
                    settings.default_unit_size,
                    _optional_float(payload.get("maxDailyRiskUnits") or payload.get("max_daily_risk_units")),
                    settings.max_units_per_bet,
                    settings.max_bets_per_slate,
                    settings.max_exposure_per_game_units,
                    settings.max_exposure_per_player_units,
                    settings.staking_method,
                    1 if settings.conservative_mode else 0,
                    utc_now(),
                ),
            )


def _row_to_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bankroll": row.get("bankroll_amount"),
        "defaultUnitSize": row.get("unit_size"),
        "maxUnitsPerBet": row.get("max_pick_risk_units"),
        "maxBetsPerSlate": row.get("max_bets_per_slate"),
        "maxExposurePerGameUnits": row.get("max_exposure_per_game_units"),
        "maxExposurePerPlayerUnits": row.get("max_exposure_per_player_units"),
        "stakingMethod": row.get("staking_method"),
        "conservativeMode": bool(row.get("conservative_mode")),
    }


def _optional_float(value: Any) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
