from __future__ import annotations

import json
from pathlib import Path

from mlb_app.config import Settings
from mlb_app.services.model_card_service import ModelCardService


def test_model_cards_default_to_research_when_artifacts_missing(tmp_path: Path) -> None:
    settings = Settings.from_env(tmp_path)
    payload = ModelCardService(settings).payload()

    assert payload["status"] == "ok"
    assert payload["summary"]["totalMarkets"] >= 1
    first = payload["markets"][0]
    assert first["canShowConfidentPick"] is False
    assert first["decisionPolicy"]["primaryLabel"] in {"No bet", "Watchlist", "Model lean"}
    assert "trustWarnings" in first


def test_model_card_includes_latest_graded_date_when_available(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    health_dir = data_dir / "health"
    health_dir.mkdir(parents=True)
    (health_dir / "latest_grading_summary.json").write_text(
        json.dumps(
            {
                "date": "2026-05-06",
                "ok": True,
                "counts": {
                    "backtestRowsForDate": 4,
                    "gradedBacktestRowsForDate": 4,
                },
                "warnings": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    settings = Settings.from_env(tmp_path)
    card = ModelCardService(settings).card_for_market("batter_hits")

    assert card["latestGradedDate"] == "2026-05-06"


def test_model_card_reads_market_backtest_metrics(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "backtests"
    data_dir.mkdir(parents=True)
    (data_dir / "playerboard_backtest.csv").write_text(
        "market,result,profit,roi,brier_score,log_loss,clv_percent\n"
        "batter_hits,win,0.91,0.91,0.21,0.65,1.2\n"
        "batter_hits,loss,-1,-1,0.31,0.82,-0.4\n"
        "pitcher_strikeouts,win,0.87,0.87,0.18,0.58,2.0\n",
        encoding="utf-8",
    )

    settings = Settings.from_env(tmp_path)
    card = ModelCardService(settings).card_for_market("batter_hits")

    assert card["backtest"]["graded"] == 2
    assert card["backtest"]["wins"] == 1
    assert card["backtest"]["losses"] == 1
    assert card["backtest"]["winRatePercent"] == 50.0
    assert card["backtest"]["brierScore"] == 0.26


def test_model_card_reads_summary_backtest_rows(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "backtests"
    data_dir.mkdir(parents=True)
    (data_dir / "playerboard_backtest_summary.csv").write_text(
        "market,graded,wins,losses,pushes,profit,roi,brier_score,log_loss,clv_percent\n"
        "batter_hits,426,188,238,0,-47.07,-11.05,0.24,0.71,0.8\n",
        encoding="utf-8",
    )

    settings = Settings.from_env(tmp_path)
    card = ModelCardService(settings).card_for_market("batter_hits")

    assert card["backtest"]["graded"] == 426
    assert card["backtest"]["wins"] == 188
    assert card["backtest"]["losses"] == 238
    assert card["backtest"]["roiPercent"] == -11.05

from mlb_app.services.model_card_service import ModelSnapshotCache


class CountingCsvStore:
    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def read_rows(self, path: Path) -> list[dict[str, str]]:
        key = str(path)
        self.calls[key] = self.calls.get(key, 0) + 1
        if path.name == "playerboard_backtest_summary.csv" and path.exists():
            return [
                {
                    "market": "batter_hits",
                    "graded": "10",
                    "wins": "6",
                    "losses": "4",
                    "roi": "12.5",
                }
            ]
        return []


def test_model_card_snapshot_reuses_backtest_rows_within_ttl(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "backtests"
    data_dir.mkdir(parents=True)
    (data_dir / "playerboard_backtest_summary.csv").write_text(
        "market,graded,wins,losses,roi\nbatter_hits,10,6,4,12.5\n",
        encoding="utf-8",
    )
    settings = Settings.from_env(tmp_path)
    csv_store = CountingCsvStore()
    cache = ModelSnapshotCache(ttl_seconds=30)
    service = ModelCardService(settings, csv_store=csv_store, snapshot_cache=cache)

    first = service.payload({"market": ["batter_hits"]})
    second = service.payload({"market": ["batter_hits"]})

    assert first["modelSnapshot"]["hit"] is False
    assert second["modelSnapshot"]["hit"] is True
    summary_path = str(settings.data_dir / "backtests" / "playerboard_backtest_summary.csv")
    assert csv_store.calls[summary_path] == 1


def test_model_card_snapshot_invalidates_when_backtest_file_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "backtests"
    data_dir.mkdir(parents=True)
    source = data_dir / "playerboard_backtest_summary.csv"
    source.write_text("market,graded,wins,losses,roi\nbatter_hits,10,6,4,12.5\n", encoding="utf-8")
    settings = Settings.from_env(tmp_path)
    cache = ModelSnapshotCache(ttl_seconds=30)
    service = ModelCardService(settings, snapshot_cache=cache)

    first = service.payload({"market": ["batter_hits"]})
    source.write_text("market,graded,wins,losses,roi\nbatter_hits,20,11,9,6.2\n", encoding="utf-8")
    second = service.payload({"market": ["batter_hits"]})

    assert first["markets"][0]["backtest"]["graded"] == 10
    assert second["modelSnapshot"]["hit"] is False
    assert second["markets"][0]["backtest"]["graded"] == 20
