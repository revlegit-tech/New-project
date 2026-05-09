CREATE TABLE IF NOT EXISTS board_snapshots (
  id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  date TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  snapshot_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'inactive', 'failed', 'rolled_back')),
  source TEXT NOT NULL DEFAULT 'pipeline',
  source_mode TEXT NOT NULL DEFAULT '',
  schema_version TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  csv_path TEXT,
  active_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS board_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id TEXT NOT NULL REFERENCES board_snapshots(id) ON DELETE CASCADE,
  row_index INTEGER NOT NULL,
  prop_key TEXT NOT NULL,
  season INTEGER NOT NULL,
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  player_id TEXT,
  player_name TEXT,
  team TEXT,
  opponent TEXT,
  pitcher TEXT,
  line TEXT,
  side TEXT,
  book TEXT,
  american_odds TEXT,
  edge_percent REAL,
  probability_percent REAL,
  implied_probability_percent REAL,
  rank_score REAL,
  row_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(snapshot_id, row_index),
  UNIQUE(snapshot_id, prop_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_board_snapshots_active_scope
  ON board_snapshots(season, date, market)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_board_snapshots_status_scope
  ON board_snapshots(status, season, date, market, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_board_snapshots_created_at
  ON board_snapshots(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_board_rows_snapshot_prop_key
  ON board_rows(snapshot_id, prop_key);

CREATE INDEX IF NOT EXISTS idx_board_rows_prop_key
  ON board_rows(prop_key);

CREATE INDEX IF NOT EXISTS idx_board_rows_scope_market
  ON board_rows(season, date, market);

CREATE INDEX IF NOT EXISTS idx_board_rows_field_lookup
  ON board_rows(season, date, market, player_name, team, opponent, line, book);
