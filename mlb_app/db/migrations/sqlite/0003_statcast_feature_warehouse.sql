CREATE TABLE IF NOT EXISTS statcast_raw_rows (
  id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  feature_date TEXT NOT NULL,
  season INTEGER,
  game_id TEXT NOT NULL DEFAULT '',
  player_id TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  pitch_type TEXT NOT NULL DEFAULT '',
  split TEXT NOT NULL DEFAULT '',
  handedness TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  row_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_metric_feature_rows (
  id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  feature_date TEXT NOT NULL,
  season INTEGER,
  game_id TEXT NOT NULL DEFAULT '',
  player_id TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  pitch_type TEXT NOT NULL DEFAULT '',
  split TEXT NOT NULL DEFAULT '',
  handedness TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  row_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS game_environment_feature_rows (
  id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  feature_date TEXT NOT NULL,
  season INTEGER,
  game_id TEXT NOT NULL DEFAULT '',
  player_id TEXT NOT NULL DEFAULT '',
  player_name TEXT NOT NULL DEFAULT '',
  team TEXT NOT NULL DEFAULT '',
  opponent TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  pitch_type TEXT NOT NULL DEFAULT '',
  split TEXT NOT NULL DEFAULT '',
  handedness TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  row_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_statcast_raw_dataset_date ON statcast_raw_rows(dataset, feature_date);
CREATE INDEX IF NOT EXISTS idx_statcast_raw_game ON statcast_raw_rows(game_id, feature_date);
CREATE INDEX IF NOT EXISTS idx_statcast_raw_player ON statcast_raw_rows(player_id, player_name, feature_date);
CREATE INDEX IF NOT EXISTS idx_player_metric_dataset_date ON player_metric_feature_rows(dataset, feature_date);
CREATE INDEX IF NOT EXISTS idx_player_metric_player ON player_metric_feature_rows(player_id, player_name, feature_date);
CREATE INDEX IF NOT EXISTS idx_player_metric_team ON player_metric_feature_rows(team, opponent, feature_date);
CREATE INDEX IF NOT EXISTS idx_game_environment_dataset_date ON game_environment_feature_rows(dataset, feature_date);
CREATE INDEX IF NOT EXISTS idx_game_environment_game ON game_environment_feature_rows(game_id, feature_date);
CREATE INDEX IF NOT EXISTS idx_game_environment_teams ON game_environment_feature_rows(home_team, away_team, feature_date);
