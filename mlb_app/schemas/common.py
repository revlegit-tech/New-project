from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class ProductState(str, Enum):
    RESEARCH = "research_mode"
    EXPERIMENTAL = "experimental_model"
    BACKTEST_POSITIVE = "backtest_positive"
    PRODUCTION_TRACKED = "production_tracked"


@dataclass(frozen=True)
class ApiMeta:
    product_state: ProductState = ProductState.RESEARCH
    generated_at: str = ""
    warnings: tuple[str, ...] = ()


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value
