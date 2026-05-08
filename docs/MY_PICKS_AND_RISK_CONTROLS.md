# My Picks and Risk Controls

This stage separates model suggestions from user-tracked picks. Saving a pick does not update model backtests, model readiness, or market promotion gates.

## APIs

- `GET /api/my-picks` returns tracked picks, bankroll settings, lifecycle states, and exposure summary.
- `POST /api/my-picks` saves a user pick. Requires `X-Baseball-Prop-Action: 1`.
- `POST /api/my-picks/update` updates status, stake units, profit units, or notes. Requires `X-Baseball-Prop-Action: 1`.
- `GET /api/bankroll/settings` returns conservative bankroll defaults.
- `POST /api/bankroll/settings` updates bankroll and cap settings. Requires `X-Baseball-Prop-Action: 1`.
- `GET /api/exposure/summary` returns active exposure grouped by game, player, and market.

## Lifecycle

A pick may be `Watching`, `Placed`, `Void`, `Won`, `Lost`, `Pushed`, or `Cashout`.

`Watching` and `Placed` are active exposure states. Settled states contribute to tracked user P/L, not model backtests.

## Conservative defaults

Default settings are intentionally conservative:

- Bankroll: `$1,000`
- Unit size: `$10`
- Max units per bet: `0.5u`
- Max bets per slate: `12`
- Max exposure per game: `1.5u`
- Max exposure per player: `0.75u`
- Staking method: `flat`

Research-only picks are saved at `0u` by default, even if a larger stake is requested.

## Storage

Local state is JSON-backed under `data/user/` and is excluded from safe source exports.
