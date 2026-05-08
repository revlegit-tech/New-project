from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentHealth:
    name: str
    status: str
    message: str = ""
    latest_date: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DataHealthSummary:
    status: str
    odds: ComponentHealth
    playerboard: ComponentHealth
    grading: ComponentHealth
    models: ComponentHealth
