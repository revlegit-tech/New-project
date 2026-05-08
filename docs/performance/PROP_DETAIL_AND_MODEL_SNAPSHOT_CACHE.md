# Phase 4 Hot-Path Continuation: Prop Detail and Model Snapshot Cache

## Objective

Reduce repeated service fan-out after the EdgeBoard cache is in place.

The detail path now follows this order:

1. `PropDetailService` asks `EdgeBoardService` for the board using the same board query dimensions.
2. `EdgeBoardService` serves from `BoardCache` when TTL and playerboard CSV mtime/size signatures are valid.
3. `PropDetailService` finds the target row in that board.
4. If the row already includes an enriched `modelCard`, detail uses it directly.
5. `ModelCardService.card_for_market()` is only called when the board row does not include embedded model-card context.

This avoids a second model-card scan for the normal Today-board -> detail-drawer workflow.

## ModelSnapshotCache

`ModelCardService` now owns a process-local, thread-safe `ModelSnapshotCache` with a default 30-second TTL.

The snapshot contains:

- model registry JSON
- grading payload
- backtest source path
- backtest rows
- per-market status memoization for the current snapshot object
- file signatures for mtime-aware invalidation

The cache invalidates when:

- TTL expires
- the model registry file changes
- the latest grading summary changes
- a backtest CSV/JSON candidate changes or appears

## Trust-surface behavior

No new betting markets are unlocked by this patch. Missing model-card data remains conservative and falls back to `Research only` / `No model` behavior.

## Contract additions

`/api/model-cards` now includes non-sensitive snapshot metadata:

```json
{
  "modelSnapshot": {
    "hit": true,
    "reason": "hit",
    "ageSeconds": 2.2,
    "ttlRemainingSeconds": 27.8,
    "backtestSource": "data/backtests/playerboard_backtest_summary.csv",
    "backtestRows": 6
  }
}
```

`/api/prop-detail` now includes source metadata:

```json
{
  "source": {
    "boardCache": {"hit": true, "reason": "hit"},
    "modelCardSource": "edge_board_row"
  }
}
```
