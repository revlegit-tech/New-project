from __future__ import annotations

import re
from typing import Any


_SIDE_PATTERN = re.compile(r"\b(over|under)\b", re.IGNORECASE)


def normalize_prop_side(
    existing_side: Any = "",
    raw_label: Any = "",
    label: Any = "",
    outcome: Any = "",
) -> str:
    """Return canonical Over/Under when present, otherwise preserve safe input."""

    values = (existing_side, raw_label, label, outcome)
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        match = _SIDE_PATTERN.search(text)
        if match:
            return match.group(1).title()
    for value in (existing_side, outcome, label):
        text = str(value or "").strip()
        if text:
            return text
    return ""
