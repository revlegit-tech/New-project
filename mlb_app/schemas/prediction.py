from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictionRequest:
    market: str
    player: str
    team: str = ""
    opponent: str = ""
    line: float = 0.0
    american_odds: float = -110.0


@dataclass(frozen=True)
class ModelReadiness:
    market: str
    status: str
    reason: str
    training_rows: int = 0
    positive_rows: int = 0
    negative_rows: int = 0
    artifact: str = ""
    trained_at: str = ""
    calibrated: bool = False
