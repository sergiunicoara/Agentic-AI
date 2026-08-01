-- files.content stores the exact raw source of each ingested file, so /file can
-- serve the citation viewer directly from Postgres. Chunks alone don't fully tile
-- every file (module-preamble only covers lines before the first top-level def),
-- so reconstructing raw content purely from chunks would have gaps.
ALTER TABLE files ADD COLUMN IF NOT EXISTS content TEXT NOT NULL DEFAULT '';
