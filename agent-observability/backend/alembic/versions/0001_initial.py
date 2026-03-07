"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(256), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("task_id", sa.String(128)),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_traces_agent_name", "agent_traces", ["agent_name"])

    op.create_table(
        "spans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "trace_id",
            sa.String(36),
            sa.ForeignKey("agent_traces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("parent_span_id", sa.String(36)),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger, nullable=False),
        sa.Column("duration_ms", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("model", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text),
        sa.Column("attributes", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("trace_id", sa.String(36)),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
    )

    op.create_table(
        "eval_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36)),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("spans")
    op.drop_table("agent_traces")
    op.drop_table("users")
