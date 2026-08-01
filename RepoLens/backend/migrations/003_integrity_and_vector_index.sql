-- Integrity constraints and scalable vector retrieval for existing installations.
CREATE UNIQUE INDEX IF NOT EXISTS uq_repos_source_url ON repos(source_url);
CREATE UNIQUE INDEX IF NOT EXISTS uq_files_repo_path ON files(repo_id, path);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
ON chunks USING hnsw (embedding vector_cosine_ops);

DO $$
BEGIN
    ALTER TABLE chunks
        ADD CONSTRAINT ck_chunk_lines CHECK (start_line >= 1 AND end_line >= start_line);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE messages
        ADD CONSTRAINT ck_message_role CHECK (role IN ('user', 'assistant'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
