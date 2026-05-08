from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COORDS = ROOT / "data" / "reference" / "mlb_venue_coordinates.csv"


def test_coordinate_file_has_all_current_mlb_venues():
    with COORDS.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 30
    venues = {row["venue"] for row in rows}
    assert "Yankee Stadium" in venues
    assert "Petco Park" in venues
    assert "Sutter Health Park" in venues
    assert "Nationals Park" in venues


def test_coordinates_are_numeric_and_in_range():
    with COORDS.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        lat = float(row["latitude"])
        lon = float(row["longitude"])
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180
        assert row["coordinate_source"] == "user_provided_phase17_v5"
