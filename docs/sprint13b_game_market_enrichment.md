# Sprint 13B Game-Market Enrichment

Sprint 13B enriches Playerboard, EdgeBoard, and the research report with safe pregame game-market context from Sprint 13A historical game odds features.

This does not replace the PropLine player-prop pipeline. If the warehouse is disabled, unavailable, missing tables, or has no matching game, the prop rows still render with `game_market_available=false` and a row-level `game_market_enrichment_status`.

## Added Row Fields

The enrichment fields are prefixed with `game_market_` to avoid collisions:

- `game_market_available`
- `game_market_game_id`
- `game_market_consensus_open_total`
- `game_market_consensus_current_total`
- `game_market_total_line_movement`
- `game_market_favorite_team_open`
- `game_market_favorite_team_current`
- `game_market_team_is_favorite_open`
- `game_market_team_is_favorite_current`
- `game_market_team_no_vig_win_prob_open`
- `game_market_team_no_vig_win_prob_current`
- `game_market_opponent_no_vig_win_prob_open`
- `game_market_opponent_no_vig_win_prob_current`
- `game_market_book_count_moneyline`
- `game_market_book_count_total`
- `game_market_book_count_runline`
- `game_market_disagreement_score`
- `game_market_team_moneyline_movement`
- `game_market_opponent_moneyline_movement`
- `game_market_quality_flags`
- `game_market_enrichment_status`

Status values:

- `matched`
- `missing_date`
- `missing_team`
- `missing_opponent`
- `ambiguous_match`
- `warehouse_unavailable`
- `not_found`

## Matching Logic

Rows are matched by:

1. Prop row date.
2. Canonical team abbreviation.
3. Canonical opponent abbreviation.
4. Historical feature row where `(away_team, home_team)` matches either team/opponent order.

Team aliases are normalized through `mlb_app/services/team_match_utils.py`. The helper supports common variants such as `ARI/AZ`, `CWS/CHW`, `KC/KCR`, `SD/SDP`, `SF/SFG`, `TB/TBR`, and `WSH/WAS/WSN`.

The lookup deliberately avoids fuzzy matching. If more than one feature row matches the same date/team/opponent, the row is marked `ambiguous_match` instead of guessing.

## Performance

The lookup batches by date. Playerboard and EdgeBoard collect row contexts, query `historical_game_market_features` at most once per unique date, and enrich rows in memory.

## Leakage Rules

Pregame board/report enrichment never exposes final-score or grading outcome fields, including:

- `home_score`
- `away_score`
- `total_runs`
- `home_win`
- `away_win`
- `game_status`
- `gameStatusText`
- `result`
- `profit_1u`
- grade result fields

Those fields remain limited to historical game odds grade endpoints.

## Config

`GAME_MARKET_ENRICHMENT_ENABLED=1` enables enrichment. It defaults to enabled because lookup failures are treated as safe row-level fallbacks.

Related warehouse flags:

- `DB_ENABLED`
- `DATABASE_URL`
- `DB_FALLBACK_TO_CSV`

The app continues to work with `DB_ENABLED=0` and CSV fallback only.

## Endpoint Examples

Playerboard:

```text
/api/playerboard?season=2026&date=2026-06-22&limit=25
```

EdgeBoard:

```text
/api/edge-board?date=2026-06-22&limit=25
```

Research report:

```text
/api/research/report?date=2026-06-22&limit=100
```

Data status now includes `game_market_enrichment`:

```text
/api/data/status
```

Example section:

```json
{
  "enabled": true,
  "source": "historical_game_market_features",
  "historical_game_odds_available": true,
  "feature_rows": 2430,
  "latest_feature_date": "2026-06-22",
  "matched_rows_last_request": 18,
  "fallback_mode": "standby",
  "warnings": []
}
```

## Research Report Context

Report cards add cautious context lines such as:

- `Game total moved up`
- `Market expects lower run environment`
- `Team is a current market favorite`
- `Large market disagreement; treat as volatile`
- `No game-market context available`

These are explanatory notes only and do not change the model ranking score.

## Sprint 13C Handoff

Sprint 13C can promote the safe `game_market_*` fields into ML feature pipelines after:

1. Confirming no leakage fields enter training inputs.
2. Measuring coverage by market/date.
3. Adding missingness indicators for unmatched rows.
4. Validating whether totals movement, no-vig win probability, favorite status, and disagreement improve out-of-sample calibration.
