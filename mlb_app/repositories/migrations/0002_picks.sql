CREATE TABLE IF NOT EXISTS picks (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  game_id TEXT,
  player_id TEXT,
  player_name TEXT,
  team TEXT,
  opponent TEXT,
  market TEXT NOT NULL,
  line REAL,
  side TEXT,
  odds INTEGER,
  model_probability REAL,
  implied_probability REAL,
  edge REAL,
  stake_units REAL NOT NULL DEFAULT 0,
  stake_amount REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_picks_created_at ON picks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_picks_status ON picks(status);
CREATE INDEX IF NOT EXISTS idx_picks_market ON picks(market);
CREATE INDEX IF NOT EXISTS idx_picks_player ON picks(player_name);
