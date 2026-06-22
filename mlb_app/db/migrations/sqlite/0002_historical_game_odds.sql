CREATE TABLE IF NOT EXISTS historical_game_odds_imports (
  import_id TEXT PRIMARY KEY,
  source_file TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT '',
  finished_at TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  games_read INTEGER NOT NULL DEFAULT 0,
  games_imported INTEGER NOT NULL DEFAULT 0,
  line_rows_imported INTEGER NOT NULL DEFAULT 0,
  feature_rows_written INTEGER NOT NULL DEFAULT 0,
  grade_rows_written INTEGER NOT NULL DEFAULT 0,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  errors_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_game_odds_games (
  game_id TEXT PRIMARY KEY,
  game_date TEXT NOT NULL,
  season INTEGER NOT NULL,
  start_time_utc TEXT NOT NULL DEFAULT '',
  game_type TEXT NOT NULL DEFAULT '',
  venue TEXT NOT NULL DEFAULT '',
  away_team TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  away_score INTEGER,
  home_score INTEGER,
  game_status TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_game_odds_lines (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL,
  game_date TEXT NOT NULL,
  sportsbook TEXT NOT NULL DEFAULT '',
  market TEXT NOT NULL DEFAULT '',
  side TEXT NOT NULL DEFAULT '',
  opening_odds INTEGER,
  current_odds INTEGER,
  opening_line REAL,
  current_line REAL,
  opening_implied_prob REAL,
  current_implied_prob REAL,
  opening_no_vig_prob REAL,
  current_no_vig_prob REAL,
  odds_movement REAL,
  line_movement REAL,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(game_id, sportsbook, market, side)
);

CREATE TABLE IF NOT EXISTS historical_game_market_features (
  game_id TEXT PRIMARY KEY,
  game_date TEXT NOT NULL,
  season INTEGER NOT NULL,
  away_team TEXT NOT NULL DEFAULT '',
  home_team TEXT NOT NULL DEFAULT '',
  venue TEXT NOT NULL DEFAULT '',
  consensus_open_total REAL,
  consensus_current_total REAL,
  total_line_movement REAL,
  home_open_moneyline_consensus REAL,
  away_open_moneyline_consensus REAL,
  home_current_moneyline_consensus REAL,
  away_current_moneyline_consensus REAL,
  home_no_vig_win_prob_open REAL,
  away_no_vig_win_prob_open REAL,
  home_no_vig_win_prob_current REAL,
  away_no_vig_win_prob_current REAL,
  favorite_team_open TEXT NOT NULL DEFAULT '',
  favorite_team_current TEXT NOT NULL DEFAULT '',
  book_count_moneyline INTEGER NOT NULL DEFAULT 0,
  book_count_total INTEGER NOT NULL DEFAULT 0,
  book_count_runline INTEGER NOT NULL DEFAULT 0,
  market_disagreement_score REAL,
  quality_flags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_game_market_grades (
  id TEXT PRIMARY KEY,
  game_id TEXT NOT NULL,
  game_date TEXT NOT NULL,
  sportsbook TEXT NOT NULL DEFAULT '',
  market TEXT NOT NULL DEFAULT '',
  side TEXT NOT NULL DEFAULT '',
  line REAL,
  odds INTEGER,
  result TEXT NOT NULL DEFAULT '',
  push_flag INTEGER NOT NULL DEFAULT 0,
  profit_1u REAL,
  closing_line_value REAL,
  graded_at TEXT NOT NULL,
  UNIQUE(game_id, sportsbook, market, side)
);

CREATE INDEX IF NOT EXISTS idx_hgo_imports_latest ON historical_game_odds_imports(started_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hgo_games_date ON historical_game_odds_games(game_date);
CREATE INDEX IF NOT EXISTS idx_hgo_games_teams ON historical_game_odds_games(game_date, away_team, home_team);
CREATE INDEX IF NOT EXISTS idx_hgo_lines_game ON historical_game_odds_lines(game_id);
CREATE INDEX IF NOT EXISTS idx_hgo_lines_date ON historical_game_odds_lines(game_date);
CREATE INDEX IF NOT EXISTS idx_hgo_lines_market ON historical_game_odds_lines(market);
CREATE INDEX IF NOT EXISTS idx_hgo_lines_book ON historical_game_odds_lines(sportsbook);
CREATE INDEX IF NOT EXISTS idx_hgo_lines_date_market_book ON historical_game_odds_lines(game_date, market, sportsbook);
CREATE INDEX IF NOT EXISTS idx_hgo_features_date ON historical_game_market_features(game_date);
CREATE INDEX IF NOT EXISTS idx_hgo_features_teams ON historical_game_market_features(game_date, away_team, home_team);
CREATE INDEX IF NOT EXISTS idx_hgo_grades_game ON historical_game_market_grades(game_id);
CREATE INDEX IF NOT EXISTS idx_hgo_grades_date ON historical_game_market_grades(game_date);
CREATE INDEX IF NOT EXISTS idx_hgo_grades_market ON historical_game_market_grades(market);
CREATE INDEX IF NOT EXISTS idx_hgo_grades_book ON historical_game_market_grades(sportsbook);
