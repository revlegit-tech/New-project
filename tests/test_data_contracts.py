from __future__ import annotations

from pathlib import Path

from mlb_app.contracts.data_contracts import DataContract, validate_contract


def test_data_contract_accepts_valid_csv(tmp_path: Path) -> None:
    path = tmp_path / "playerboard.csv"
    path.write_text("date,market,player,team,line\n2026-05-01,batter_hits,A Batter,NYY,0.5\n", encoding="utf-8")
    contract = DataContract(
        name="playerboard",
        path_glob="playerboard.csv",
        required_columns=("date", "market", "player", "team", "line"),
        numeric_columns=("line",),
        date_columns=("date",),
    )

    result = validate_contract(tmp_path, contract)[0]

    assert result.ok is True
    assert result.row_count == 1


def test_data_contract_fails_missing_columns_and_bad_types(tmp_path: Path) -> None:
    path = tmp_path / "playerboard.csv"
    path.write_text("date,market,player,line\nnot-a-date,batter_hits,A Batter,abc\n", encoding="utf-8")
    contract = DataContract(
        name="playerboard",
        path_glob="playerboard.csv",
        required_columns=("date", "market", "player", "team", "line"),
        numeric_columns=("line",),
        date_columns=("date",),
    )

    result = validate_contract(tmp_path, contract)[0]

    assert result.status == "failed"
    assert result.missing_columns == ("team",)
