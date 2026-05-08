# Phase 22 v3 Fixture Metadata Fallback

Adds `tools/phase22_v3_fixture_metadata_fallback.py`.

Use this when OddsPapi `odds-by-tournaments` returns `fixtureId`, `participant1Id`, and `participant2Id`, but `/v4/fixtures` and `/v4/participants` are blocked by key/plan.

This fills metadata only:

- `oddspapi_fixture_id`
- `oddspapi_fixture_status`
- `oddspapi_bookmakers`
- `oddspapi_raw_snapshot_path`
- `oddspapi_provider_status`
- `oddspapi_provider_note`
- `oddspapi_matched_at`

It does not fabricate CLV, opening lines, movement, totals, or implied runs.
