from __future__ import annotations

# Compatibility wrapper. Production implementation moved under mlb_app.domain.unified_prop_context.
from mlb_app.domain.unified_prop_context import *  # noqa: F401,F403


if __name__ == "__main__":
    from mlb_app.domain.unified_prop_context import main

    raise SystemExit(main())
