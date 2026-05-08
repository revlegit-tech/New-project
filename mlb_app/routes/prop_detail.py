from __future__ import annotations

from typing import Any

from mlb_app.http import RequestContext
from mlb_app.services.prop_detail_service import PropDetailService


def prop_detail(context: RequestContext) -> dict[str, Any]:
    return PropDetailService().payload(context.query)
