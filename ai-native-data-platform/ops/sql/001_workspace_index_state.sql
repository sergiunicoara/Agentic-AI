-- Workspace-scoped index state for zero-downtime embedding reindex.
--
-- scripts/init_db.sql (the baseline schema) already creates this same
-- table, so on a normal fresh setup this file is a no-op — CREATE TABLE
-- IF NOT EXISTS silently skips it. It exists for a deployment that
-- predates workspace_index_state being part of the baseline schema and
-- needs to add it standalone.
--
-- workspace_id must be TEXT, matching workspace.id (scripts/init_db.sql)
-- and every FK/query that joins against it (e.g. app.workspace_id in
-- app/core/config.py, 'demo' as the seeded workspace id) — this
-- previously declared `uuid`, which would only ever matter if this file
-- were applied *before* scripts/init_db.sql (their CREATE TABLE IF NOT
-- EXISTS would then no-op against the wrong type), but was a real
-- landmine for exactly that "predates the baseline schema" case this
-- file is meant to cover.
--
-- Apply with:
--   psql "$DATABASE_URL" -f ops/sql/001_workspace_index_state.sql

CREATE TABLE IF NOT EXISTS workspace_index_state (
  workspace_id text PRIMARY KEY,
  active_embedding_version text NOT NULL,
  target_embedding_version text NULL,
  index_epoch integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Helpful for admin dashboards / audit.
CREATE INDEX IF NOT EXISTS workspace_index_state_updated_at_idx
  ON workspace_index_state (updated_at DESC);
