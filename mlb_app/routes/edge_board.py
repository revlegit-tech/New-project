from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.edge_board_service import EdgeBoardService


def edge_board(context: RequestContext) -> dict[str, Any]:
    return EdgeBoardService().payload(context.query)
