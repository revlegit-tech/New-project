# PropLine Daily Refresh

The Outlier board does not call PropLine directly. It reads local, dated source files:

- `data/odds/propline_props_YYYY-MM-DD.csv`
- `data/warehouse/odds_snapshots/propline_props_YYYY-MM-DD_*.csv`
- `data/playerboard/playerboard_YYYY.csv`

If the UI says `No PropLine props found for this date yet`, fetch the source props first, then rebuild the playerboard.

```powershell
$Date = "2026-05-07"
python tools/fetch_propline_props.py --date $Date
python season_auto_collector.py snapshot --date $Date --run-type manual
python playerboard.py --season 2026 --date $Date --limit 500 --market ""
```

Then restart or wait 30 seconds for BoardCache TTL expiry and refresh:

```text
http://127.0.0.1:8765/?view=outlier
http://127.0.0.1:8765/api/edge-board?date=2026-05-07&buildIfMissing=1
```

The admin HTTP sync endpoint exists for local/staging operator workflows only:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8765/api/admin/propline/props/sync?date=2026-05-07" `
  -Headers @{ "X-Baseball-Prop-Action" = "1" }
```

Do not expose this endpoint as a public bettor-facing UI action. It consumes external API quota and is protected by the mutation security boundary.
