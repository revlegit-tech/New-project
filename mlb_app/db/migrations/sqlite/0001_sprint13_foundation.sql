CREATE TABLE IF NOT EXISTS collector_runs (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  date TEXT NOT NULL,
  run_type TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT '',
  finished_at TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT '',
  props_loaded INTEGER NOT NULL DEFAULT 0,
  playerboard_rows INTEGER NOT NULL DEFAULT 0,
  edge_board_rows INTEGER NOT NULL DEFAULT 0,
  artifact_name TEXT NOT NULL DEFAULT '',
  manifest_path TEXT NOT NULL DEFAULT '',
  warnings_json TEXT NOT NULL DEFAULT '[]',
  errors_json TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_manifests (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL DEFAULT '',
  date TEXT NOT NULL DEFAULT '',
  manifest_path TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
  id TEXT PRIMARY KEY,
  team_code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  league TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
  id TEXT PRIMARY KEY,
  source_player_id TEXT NOT NULL UNIQUE,
  player_name TEXT NOT NULL,
  current_team TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY,
  source_game_id TEXT NOT NULL UNIQUE,
  date TEXT NOT NULL,
  home_team TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  start_time TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS props (
  id TEXT PRIMARY KEY,
  source_prop_key TEXT NOT NULL UNIQUE,
  date TEXT NOT NULL,
  game_id TEXT NOT NULL DEFAULT '',
  player_id TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  market TEXT NOT NULL DEFAULT '',
  line TEXT NOT NULL DEFAULT '',
  side TEXT NOT NULL DEFAULT '',
  book TEXT NOT NULL DEFAULT '',
  american_odds TEXT NOT NULL DEFAULT '',
  implied_probability REAL,
  source TEXT NOT NULL DEFAULT '',
  source_event_id TEXT NOT NULL DEFAULT '',
  source_prop_id TEXT NOT NULL DEFAULT '',
  collected_at TEXT NOT NULL DEFAULT '',
  raw_file_id TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
  id TEXT PRIMARY KEY,
  source_snapshot_key TEXT NOT NULL UNIQUE,
  date TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  line TEXT NOT NULL DEFAULT '',
  side TEXT NOT NULL DEFAULT '',
  book TEXT NOT NULL DEFAULT '',
  american_odds TEXT NOT NULL DEFAULT '',
  implied_probability REAL,
  source_path TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playerboard_snapshots (
  id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  date TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  row_index INTEGER NOT NULL DEFAULT 0,
  prop_key TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  player_id TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  line TEXT NOT NULL DEFAULT '',
  book TEXT NOT NULL DEFAULT '',
  american_odds TEXT NOT NULL DEFAULT '',
  model_probability REAL,
  implied_probability REAL,
  edge_percent REAL,
  confidence TEXT NOT NULL DEFAULT '',
  freshness_status TEXT NOT NULL DEFAULT '',
  source_run_id TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  row_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(date, market, prop_key, snapshot_at)
);

CREATE TABLE IF NOT EXISTS edge_board_snapshots (
  id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  date TEXT NOT NULL,
  snapshot_at TEXT NOT NULL,
  row_index INTEGER NOT NULL DEFAULT 0,
  prop_key TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  edge_percent REAL,
  score REAL,
  decision_label TEXT NOT NULL DEFAULT '',
  source_run_id TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  row_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(date, market, prop_key, snapshot_at)
);

CREATE TABLE IF NOT EXISTS research_reports (
  id TEXT PRIMARY KEY,
  season INTEGER NOT NULL,
  date TEXT NOT NULL,
  report_key TEXT NOT NULL DEFAULT 'daily',
  generated_at TEXT NOT NULL,
  source_snapshot_id TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(date, report_key, generated_at)
);

CREATE TABLE IF NOT EXISTS model_grades (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  prop_key TEXT NOT NULL DEFAULT '',
  grade_status TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',
  closing_line TEXT NOT NULL DEFAULT '',
  closing_odds TEXT NOT NULL DEFAULT '',
  clv REAL,
  roi REAL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(date, market, prop_key)
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  date TEXT NOT NULL DEFAULT '',
  route TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_collector_runs_date ON collector_runs(date, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_manifests_date ON data_manifests(date, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_games_date ON games(date);
CREATE INDEX IF NOT EXISTS idx_props_date_market ON props(date, market);
CREATE INDEX IF NOT EXISTS idx_props_player ON props(player_name, date);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_date_market ON odds_snapshots(date, market, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_playerboard_snapshots_latest ON playerboard_snapshots(season, date, market, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_playerboard_snapshots_prop ON playerboard_snapshots(prop_key, date);
CREATE INDEX IF NOT EXISTS idx_edge_board_snapshots_latest ON edge_board_snapshots(season, date, market, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_reports_latest ON research_reports(season, date, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_grades_market_date ON model_grades(market, date);
CREATE INDEX IF NOT EXISTS idx_audit_events_type_date ON audit_events(event_type, created_at DESC);
