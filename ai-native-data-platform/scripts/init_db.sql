CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workspace (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_api_key (
  id SERIAL PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  api_key TEXT,
  api_key_hash TEXT NOT NULL,
  api_key_prefix TEXT NOT NULL,
  UNIQUE(workspace_id),
  UNIQUE(api_key_hash)
);

-- One-time migration from the original plaintext demo key column. The old
-- value is scrubbed after its digest has been recorded.
ALTER TABLE workspace_api_key ADD COLUMN IF NOT EXISTS api_key_hash TEXT;
ALTER TABLE workspace_api_key ADD COLUMN IF NOT EXISTS api_key_prefix TEXT;
ALTER TABLE workspace_api_key ALTER COLUMN api_key DROP NOT NULL;
UPDATE workspace_api_key
SET api_key_hash = encode(digest(api_key, 'sha256'), 'hex'),
    api_key_prefix = left(api_key, 8),
    api_key = NULL
WHERE api_key_hash IS NULL AND api_key IS NOT NULL;
ALTER TABLE workspace_api_key ALTER COLUMN api_key_hash SET NOT NULL;
ALTER TABLE workspace_api_key ALTER COLUMN api_key_prefix SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_api_key_hash ON workspace_api_key (api_key_hash);

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
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  status TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

ALTER TABLE ingestion_run ADD COLUMN IF NOT EXISTS workspace_id TEXT;
UPDATE ingestion_run r
SET workspace_id = d.workspace_id
FROM document d
WHERE r.document_id = d.id AND r.workspace_id IS NULL;
ALTER TABLE ingestion_run ALTER COLUMN workspace_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ingestion_run_workspace_created ON ingestion_run (workspace_id, created_at DESC);

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
ALTER TABLE document_chunk ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE document_chunk DROP CONSTRAINT IF EXISTS document_chunk_workspace_id_fkey;
ALTER TABLE document_chunk ADD CONSTRAINT document_chunk_workspace_id_fkey
  FOREIGN KEY (workspace_id) REFERENCES workspace(id);

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

-- Tenant isolation is enforced twice: query predicates in application code and
-- Postgres RLS. Every application access to these tables uses
-- workspace_session_scope(), which sets app.workspace_id transaction-locally.
ALTER TABLE document ENABLE ROW LEVEL SECURITY;
ALTER TABLE document FORCE ROW LEVEL SECURITY;
ALTER TABLE document_chunk ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunk FORCE ROW LEVEL SECURITY;
ALTER TABLE ingestion_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_run FORCE ROW LEVEL SECURITY;
ALTER TABLE trace_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE trace_log FORCE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_trace_type_created
ON trace_log (trace_type, created_at DESC);

-- Multimodal image chunks: vision-captioned pages/images for unified retrieval.
CREATE TABLE IF NOT EXISTS image_chunk (
  id UUID PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  document_id UUID REFERENCES document(id),   -- NULL for standalone images
  source_name TEXT NOT NULL,
  external_id TEXT,
  page_number INT NOT NULL DEFAULT 0,
  caption TEXT NOT NULL,                       -- generated by vision model (GPT-4o / Gemini)
  embedding vector(384) NOT NULL,              -- caption embedding for semantic search
  embedding_version TEXT NOT NULL,
  image_hash TEXT NOT NULL,                    -- SHA-256 of raw image bytes for dedup
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(image_hash, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_image_chunk_workspace
ON image_chunk (workspace_id);

-- ANN index for image caption embeddings — same cosine ops as document_chunk.
CREATE INDEX IF NOT EXISTS idx_image_chunk_embedding
ON image_chunk USING ivfflat (embedding vector_cosine_ops);

-- Audit log for natural-language queries (NLP → SQL layer).
-- Captures every query regardless of success/failure for compliance + debugging.
CREATE TABLE IF NOT EXISTS nl_query_audit_log (
  id UUID PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  nl_query TEXT NOT NULL,
  generated_sql TEXT NOT NULL,
  params JSONB NOT NULL DEFAULT '{}',
  row_count INT NOT NULL DEFAULT 0,
  latency_ms INT NOT NULL,
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nl_audit_workspace_created
ON nl_query_audit_log (workspace_id, created_at DESC);

ALTER TABLE image_chunk ENABLE ROW LEVEL SECURITY;
ALTER TABLE image_chunk FORCE ROW LEVEL SECURITY;
ALTER TABLE nl_query_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_query_audit_log FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_document ON document;
CREATE POLICY tenant_document ON document
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
DROP POLICY IF EXISTS tenant_document_chunk ON document_chunk;
CREATE POLICY tenant_document_chunk ON document_chunk
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
DROP POLICY IF EXISTS tenant_ingestion_run ON ingestion_run;
CREATE POLICY tenant_ingestion_run ON ingestion_run
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
DROP POLICY IF EXISTS tenant_trace_log ON trace_log;
CREATE POLICY tenant_trace_log ON trace_log
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
DROP POLICY IF EXISTS tenant_image_chunk ON image_chunk;
CREATE POLICY tenant_image_chunk ON image_chunk
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));
DROP POLICY IF EXISTS tenant_nl_query_audit_log ON nl_query_audit_log;
CREATE POLICY tenant_nl_query_audit_log ON nl_query_audit_log
  USING (workspace_id = current_setting('app.workspace_id', true))
  WITH CHECK (workspace_id = current_setting('app.workspace_id', true));

-- Seed helper workspace.
INSERT INTO workspace (id, name)
VALUES ('demo', 'Demo')
ON CONFLICT (id) DO NOTHING;

INSERT INTO workspace_api_key (workspace_id, api_key_hash, api_key_prefix)
VALUES ('demo', encode(digest('demo', 'sha256'), 'hex'), 'demo')
ON CONFLICT (workspace_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS workspace_index_state (
  workspace_id  TEXT PRIMARY KEY REFERENCES workspace(id) ON DELETE CASCADE,
  active_embedding_version TEXT NOT NULL DEFAULT 'v1',
  target_embedding_version TEXT,
  index_epoch   INT NOT NULL DEFAULT 0,
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- A shared, durable remediation override. API replicas read this row before
-- assigning an experiment, replacing the previous replica-local file.
CREATE TABLE IF NOT EXISTS runtime_experiment_override (
  scope TEXT PRIMARY KEY,
  experiment TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Durable, multi-replica ingestion queue. Payloads are metadata only; image
-- bytes live in a child table so jobs survive API restarts without relying on
-- process-local queues or shared filesystems.
CREATE TABLE IF NOT EXISTS ingestion_job (
  id UUID PRIMARY KEY,
  job_type TEXT NOT NULL CHECK (job_type IN ('document', 'image')),
  workspace_id TEXT NOT NULL REFERENCES workspace(id),
  document_id UUID NULL REFERENCES document(id),
  payload JSONB NOT NULL DEFAULT '{}',
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')) DEFAULT 'queued',
  attempts INT NOT NULL DEFAULT 0,
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_at TIMESTAMPTZ,
  locked_by TEXT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_job_claim
ON ingestion_job (status, available_at, created_at);

CREATE TABLE IF NOT EXISTS ingestion_job_media (
  id UUID PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES ingestion_job(id) ON DELETE CASCADE,
  ordinal INT NOT NULL,
  mime_type TEXT NOT NULL,
  content BYTEA NOT NULL,
  UNIQUE (job_id, ordinal)
);
