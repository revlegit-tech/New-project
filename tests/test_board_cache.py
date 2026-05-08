from __future__ import annotations

import os
from pathlib import Path

from mlb_app.services.board_cache import BoardCache
from mlb_app.services.edge_board_service import EdgeBoardService


class Clock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakePlayerboardService:
    def __init__(self) -> None:
        self.calls = 0

    def board_payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        self.calls += 1
        return {
            "season": 2026,
            "date": "2026-05-07",
            "cacheHit": False,
            "propsLoaded": 1,
            "cardsBuilt": 1,
            "top": [
                {
                    "date": "2026-05-07",
                    "player": "Example Batter",
                    "team": "NYY",
                    "opponent": "BOS",
                    "market": "batter_hits",
                    "line": "0.5",
                    "americanOdds": "-110",
                    "finalEdgePercent": "3.2",
                    "finalProbabilityPercent": "58.1",
                    "impliedProbabilityPercent": "52.4",
                    "confidence": "Medium",
                }
            ],
            "productState": {"state": "research_mode"},
            "latestFullyGradedDate": "2026-05-06",
            "dataConfidence": "Good",
            "modelReadiness": {},
            "trust": {},
        }


class FakeModelCardService:
    def payload(self, query: dict[str, list[str]]) -> dict[str, object]:
        return {
            "markets": [
                {
                    "market": "batter_hits",
                    "readinessLabel": "Research only",
                    "productionStatus": "research_only",
                    "canShowConfidentPick": False,
                    "trainingRows": 25,
                    "positiveRows": 12,
                    "negativeRows": 13,
                    "trustWarnings": ["Insufficient production evidence."],
                    "calibration": {"status": "uncalibrated"},
                }
            ]
        }

    def card_for_market(self, market: str) -> dict[str, object]:
        return {}


def touch_with_new_mtime(path: Path, ns: int) -> None:
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    os.utime(path, ns=(ns, ns))


def test_board_cache_hits_within_ttl_when_dependency_is_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    clock = Clock()
    cache = BoardCache(ttl_seconds=30, now=clock)
    builds = {"count": 0}

    def builder() -> dict[str, object]:
        builds["count"] += 1
        return {"rows": [{"player": "A"}]}

    first = cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))
    second = cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))

    assert first.hit is False
    assert second.hit is True
    assert builds["count"] == 1
    assert cache.status()["hits"] == 1


def test_board_cache_invalidates_when_dependency_mtime_or_size_changes(tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    clock = Clock()
    cache = BoardCache(ttl_seconds=30, now=clock)
    builds = {"count": 0}

    def builder() -> dict[str, object]:
        builds["count"] += 1
        return {"generation": builds["count"]}

    first = cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))
    touch_with_new_mtime(source, 2_000_000_000)
    second = cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))

    assert first.payload["generation"] == 1
    assert second.payload["generation"] == 2
    assert second.hit is False
    assert builds["count"] == 2
    assert cache.status()["invalidations"] >= 1


def test_board_cache_expires_after_ttl(tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    clock = Clock()
    cache = BoardCache(ttl_seconds=10, now=clock)
    builds = {"count": 0}

    def builder() -> dict[str, object]:
        builds["count"] += 1
        return {"generation": builds["count"]}

    cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))
    clock.advance(11)
    result = cache.get_or_build(("edge", 2026), builder, dependency_paths=(source,))

    assert result.hit is False
    assert result.payload["generation"] == 2


def test_board_cache_returns_deepcopy_to_prevent_mutation_bleed(tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    cache = BoardCache(ttl_seconds=30)

    result = cache.get_or_build(("edge", 2026), lambda: {"rows": [{"player": "A"}]}, dependency_paths=(source,))
    result.payload["rows"][0]["player"] = "MUTATED"
    second = cache.get_or_build(("edge", 2026), lambda: {"rows": []}, dependency_paths=(source,))

    assert second.hit is True
    assert second.payload["rows"][0]["player"] == "A"


def test_edge_board_service_reuses_board_cache(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    fake_playerboard = FakePlayerboardService()
    cache = BoardCache(ttl_seconds=30)
    monkeypatch.setattr(
        "mlb_app.services.edge_board_service._playerboard_dependency_paths",
        lambda query: (source,),
    )
    service = EdgeBoardService(
        playerboard_service=fake_playerboard,
        model_card_service=FakeModelCardService(),
        board_cache=cache,
    )

    first = service.payload({"season": ["2026"], "date": ["2026-05-07"], "limit": ["50"]})
    second = service.payload({"season": ["2026"], "date": ["2026-05-07"], "limit": ["50"]})

    assert first["boardCache"]["hit"] is False
    assert second["boardCache"]["hit"] is True
    assert second["cacheHit"] is True
    assert fake_playerboard.calls == 1


def test_edge_board_service_rebuilds_when_playerboard_csv_changes(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "playerboard.csv"
    source.write_text("snapshotAt,season,date\nnow,2026,2026-05-07\n", encoding="utf-8")
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    fake_playerboard = FakePlayerboardService()
    cache = BoardCache(ttl_seconds=30)
    monkeypatch.setattr(
        "mlb_app.services.edge_board_service._playerboard_dependency_paths",
        lambda query: (source,),
    )
    service = EdgeBoardService(
        playerboard_service=fake_playerboard,
        model_card_service=FakeModelCardService(),
        board_cache=cache,
    )

    service.payload({"season": ["2026"], "date": ["2026-05-07"], "limit": ["50"]})
    touch_with_new_mtime(source, 2_000_000_000)
    payload = service.payload({"season": ["2026"], "date": ["2026-05-07"], "limit": ["50"]})

    assert payload["boardCache"]["hit"] is False
    assert fake_playerboard.calls == 2
