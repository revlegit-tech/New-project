from __future__ import annotations

from pathlib import Path

from mlb_app.config import Settings, settings as default_settings
from mlb_app.services.context_sources.base import ContextProviderResult, context_path, read_csv_rows, write_csv_rows
from mlb_app.services.game_market_context_service import CANONICAL_GAME_MARKET_FIELDS, NORMALIZED_GAME_MARKET_FIELDS


class GameMarketContextProvider:
    def __init__(self, settings: Settings = default_settings) -> None:
        self.settings = settings

    def materialize(self, *, date_label: str, season: int) -> ContextProviderResult:
        output_path = context_path(self.settings, "game_markets", f"game_markets_{date_label}.csv")
        source_path = self.settings.data_dir / "warehouse" / "normalized" / "game_markets" / f"game_markets_{date_label}.csv"
        warnings: list[str] = []
        if not source_path.is_file():
            warnings.append("Normalized game market artifact not found.")
            write_csv_rows(output_path, [], list(NORMALIZED_GAME_MARKET_FIELDS))
            return _result("missing", date_label, season, 0, output_path, warnings)
        rows = read_csv_rows(source_path)
        fields = list(CANONICAL_GAME_MARKET_FIELDS) if rows and "market_type" in rows[0] else list(NORMALIZED_GAME_MARKET_FIELDS)
        write_csv_rows(output_path, rows, fields)
        return _result("ok" if rows else "missing", date_label, season, len(rows), output_path, warnings)


def _result(status: str, date_label: str, season: int, rows: int, path: Path, warnings: list[str]) -> ContextProviderResult:
    return ContextProviderResult(status=status, date=date_label, season=season, source="game_markets", rows=rows, path=str(path), warnings=warnings)
