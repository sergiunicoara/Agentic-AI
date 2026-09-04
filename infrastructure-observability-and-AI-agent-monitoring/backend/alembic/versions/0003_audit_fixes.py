"""Drop the dead password column and add the indexes the models declare

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Login is OIDC-only since 0002; the column has been unused ever since.
    op.drop_column("users", "hashed_password")

    # Declared as index=True on the models but never created.
    op.create_index("ix_agent_traces_task_id", "agent_traces", ["task_id"])
    # Every trace listing orders by created_at DESC.
    op.create_index("ix_agent_traces_created_at", "agent_traces", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_traces_created_at", table_name="agent_traces")
    op.drop_index("ix_agent_traces_task_id", table_name="agent_traces")
    op.add_column("users", sa.Column("hashed_password", sa.String(256), nullable=True))
