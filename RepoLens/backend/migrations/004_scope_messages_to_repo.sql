-- Scope conversation history to a repository. Legacy messages cannot be assigned
-- safely, so they are removed before enforcing the upgraded schema.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS repo_id UUID;

DELETE FROM messages WHERE repo_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'messages'::regclass
          AND contype = 'f'
          AND confrelid = 'repos'::regclass
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT fk_messages_repo_id
            FOREIGN KEY (repo_id) REFERENCES repos(id) ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE messages
    ALTER COLUMN repo_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_messages_repo_conversation
ON messages(repo_id, conversation_id, created_at DESC);
