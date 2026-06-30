from __future__ import annotations

import argparse
import json

from mlb_app.config import settings
from mlb_app.services.feature_source_audit_service import FeatureSourceAuditService


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize local-first MLB prop context source artifacts.")
    parser.add_argument("--date", required=True, dest="date_label")
    parser.add_argument("--season", type=int, default=settings.current_season)
    args = parser.parse_args()

    payload = FeatureSourceAuditService(settings=settings).materialize(date_label=args.date_label, season=args.season)
    print(json.dumps({"status": "ok", "path": payload["path"], "readyFeatureGroups": payload["readyFeatureGroups"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
