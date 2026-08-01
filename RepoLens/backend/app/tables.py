import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

metadata = MetaData()

repos = Table(
    "repos",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column("source_url", Text, nullable=False),
    Column("indexed_at", TIMESTAMP(timezone=True)),
    Column("commit_sha", Text),
    Column("file_count", Integer, nullable=False, default=0),
    Column("chunk_count", Integer, nullable=False, default=0),
)

files = Table(
    "files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "repo_id", UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    ),
    Column("path", Text, nullable=False),
    Column("language", Text),
    Column("loc", Integer),
    Column("content_hash", Text, nullable=False),
    Column("content", Text, nullable=False, default=""),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "file_id", UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    ),
    Column("symbol_path", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("start_line", Integer, nullable=False),
    Column("end_line", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("embedding", Vector(1536)),
    Column("token_count", Integer),
)

messages = Table(
    "messages",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
    Column(
        "repo_id",
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("citations", JSONB),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False),
)
