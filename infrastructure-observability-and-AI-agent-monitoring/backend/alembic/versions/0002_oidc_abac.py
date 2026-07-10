"""OIDC + ABAC: add oidc_sub, department, clearance_level; make hashed_password nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "hashed_password", nullable=True)

    op.add_column("users", sa.Column("oidc_sub", sa.String(256), nullable=True))
    op.add_column("users", sa.Column("department", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("clearance_level", sa.Integer(), nullable=False, server_default="0"))

    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_sub", table_name="users")
    op.drop_column("users", "clearance_level")
    op.drop_column("users", "department")
    op.drop_column("users", "oidc_sub")
    op.alter_column("users", "hashed_password", nullable=False)
