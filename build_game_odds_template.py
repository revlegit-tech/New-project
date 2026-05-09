from __future__ import annotations

# Compatibility wrapper. Production implementation moved under mlb_app.domain.build_game_odds_template.
from mlb_app.domain.build_game_odds_template import *  # noqa: F401,F403


if __name__ == "__main__":
    from mlb_app.domain.build_game_odds_template import main

    raise SystemExit(main())
