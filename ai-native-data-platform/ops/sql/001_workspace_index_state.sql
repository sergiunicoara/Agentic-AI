-- Workspace-scoped index state for zero-downtime embedding reindex.
--
-- Apply with:
--   psql "$DATABASE_URL" -f ops/sql/001_workspace_index_state.sql

CREATE TABLE IF NOT EXISTS workspace_index_state (
  workspace_id uuid PRIMARY KEY,
  active_embedding_version text NOT NULL,
  target_embedding_version text NULL,
  index_epoch integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- Helpful for admin dashboards / audit.
CREATE INDEX IF NOT EXISTS workspace_index_state_updated_at_idx
  ON workspace_index_state (updated_at DESC);
