CREATE TABLE IF NOT EXISTS prediction_events (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  model_key TEXT NOT NULL,
  model_version TEXT,
  market TEXT NOT NULL,
  game_id TEXT,
  player_id TEXT,
  input_hash TEXT,
  output_probability REAL,
  output_edge REAL,
  artifact_sha256 TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prediction_events_created_at ON prediction_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_events_model ON prediction_events(model_key, model_version);
CREATE INDEX IF NOT EXISTS idx_prediction_events_market ON prediction_events(market);
