CREATE TABLE IF NOT EXISTS bankroll_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  bankroll_amount REAL NOT NULL,
  unit_size REAL NOT NULL,
  max_daily_risk_units REAL,
  max_pick_risk_units REAL,
  max_bets_per_slate INTEGER NOT NULL DEFAULT 12,
  max_exposure_per_game_units REAL NOT NULL DEFAULT 1.5,
  max_exposure_per_player_units REAL NOT NULL DEFAULT 0.75,
  staking_method TEXT NOT NULL DEFAULT 'flat',
  conservative_mode INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
