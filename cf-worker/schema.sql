CREATE TABLE IF NOT EXISTS scores (
  handle          TEXT    PRIMARY KEY,
  tokens_30d      INTEGER NOT NULL DEFAULT 0,
  tokens_lifetime INTEGER NOT NULL DEFAULT 0,
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tokens_30d ON scores (tokens_30d DESC);
