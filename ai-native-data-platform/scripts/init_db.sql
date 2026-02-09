CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS workspace (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_api_key (
  id SERIAL PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  api_key TEXT NOT NULL,
  UNIQUE(workspace_id),
  UNIQUE(api_key)
);

CREATE TABLE IF NOT EXISTS document (
  id UUID PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  source_name TEXT NOT NULL,
  external_id TEXT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (workspace_id, source_name, external_id)
);

CREATE TABLE IF NOT EXISTS ingestion_run (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES document(id),
  status TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS document_chunk (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES document(id),
  workspace_id TEXT NULL,
  chunk_index INT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_hash TEXT NOT NULL,
  embedding vector(384) NOT NULL,
  embedding_version TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(document_id, chunk_index, embedding_version)
);

-- Backfill / forward-compatible schema evolution for multi-tenant isolation.
ALTER TABLE document_chunk ADD COLUMN IF NOT EXISTS workspace_id TEXT;
UPDATE document_chunk c
SET workspace_id = d.workspace_id
FROM document d
WHERE c.document_id = d.id AND c.workspace_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON document_chunk (workspace_id);

-- ANN index (pgvector) for dense retrieval.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
ON document_chunk USING ivfflat (embedding vector_cosine_ops);

-- Full-text search index for hybrid retrieval.
CREATE INDEX IF NOT EXISTS idx_chunks_fts
ON document_chunk USING GIN (to_tsvector('english', chunk_text));

-- Unified trace store (retrieval traces, generation traces, online signals).
CREATE TABLE IF NOT EXISTS trace_log (
  id UUID PRIMARY KEY,
  trace_type TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  body JSONB NOT NULL,
  latency_ms INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Shard metadata for simple cross-shard consistency checks.
CREATE TABLE IF NOT EXISTS shard_state (
  id INTEGER PRIMARY KEY DEFAULT 1,
  index_epoch TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO shard_state (id, index_epoch)
VALUES (1, to_char(now(), 'YYYYMMDDHH24MI'))
ON CONFLICT (id) DO NOTHING;

-- Optional Row Level Security template (not enabled by default).
-- In production, you can enable RLS and set app.workspace_id per session.
-- ALTER TABLE document ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE document_chunk ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE trace_log ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY doc_tenant ON document USING (workspace_id = current_setting('app.workspace_id', true));
-- CREATE POLICY chunk_tenant ON document_chunk USING (workspace_id = current_setting('app.workspace_id', true));
-- CREATE POLICY trace_tenant ON trace_log USING (workspace_id = current_setting('app.workspace_id', true));

CREATE INDEX IF NOT EXISTS idx_trace_type_created
ON trace_log (trace_type, created_at DESC);

-- Seed helper workspace.
INSERT INTO workspace (id, name)
VALUES ('demo', 'Demo')
ON CONFLICT (id) DO NOTHING;

INSERT INTO workspace_api_key (workspace_id, api_key)
VALUES ('demo', 'demo')
ON CONFLICT (workspace_id) DO NOTHING;
