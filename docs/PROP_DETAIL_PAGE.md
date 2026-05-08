# Prop Detail Page + Price/Context Drilldown

The prop detail page is a bettor-facing drilldown from Today’s Edge Board. It explains why a row is visible, what price is being compared, and which trust/risk gates are still blocking confident language.

## API

```text
GET /api/prop-detail
```

Supported query fields:

```text
id, season, date, market, player, team, opponent, line, americanOdds, book
```

The endpoint returns:

- `overview`: player, matchup, market, line, odds, book, decision label, readiness label.
- `priceComparison`: best available price, book-implied probability, model fair estimate, fair American odds, and book rows when available.
- `modelExplanation`: model status, sample size, calibration, latest graded date, backtest metrics, and reasons.
- `playerContext`: season/recent/split fields when the playerboard row carries them.
- `gameContext`: park, weather, lineup, pitcher, start time, and team total when available.
- `riskContext`: missing data, trust warnings, correlation warnings, slate exposure, and suggested stake.
- `tracking`: a zero-unit default payload that saves to My Picks without changing model backtests.

## UX policy

The detail page remains research-first. It does not convert a row into a confident pick unless the model card already allows confident language. Saving from the detail page creates a user-tracked pick with `stakeUnits: 0` by default.

## Leakage policy

The service reads from the edge-board/model-card contracts. It does not query postgame outcomes to justify a pregame decision. Latest graded date and backtest metrics are shown as governance context, not as prediction-time features.
