#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mlb_app.config import Settings  # noqa: E402
from mlb_app.services.model_registry_service import DEFAULT_MARKETS, ModelRegistryService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a model-readiness audit snapshot for the trust surface.")
    parser.add_argument("--markets", nargs="*", default=list(DEFAULT_MARKETS))
    parser.add_argument("--out", default=str(ROOT / "data" / "models" / "model_readiness_audit.json"))
    args = parser.parse_args()

    service = ModelRegistryService(Settings.from_env(ROOT))
    payload = service.status_payload(tuple(args.markets))
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(out)
    print(json.dumps({"status": "ok", "out": str(out), "productionEligibleMarkets": payload.get("productionEligibleMarkets", [])}, indent=2))


if __name__ == "__main__":
    main()
