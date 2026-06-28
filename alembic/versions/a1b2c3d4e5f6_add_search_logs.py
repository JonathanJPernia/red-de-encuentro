"""add search_logs

Revision ID: a1b2c3d4e5f6
Revises: 8f3a2c1d9e4b
Create Date: 2026-06-27 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8f3a2c1d9e4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("user_hash", sa.String(length=64), nullable=True),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("query_masked", sa.String(length=255), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_search_logs_created_at"), "search_logs", ["created_at"], unique=False)
    op.create_index(op.f("ix_search_logs_source"), "search_logs", ["source"], unique=False)
    op.create_index(op.f("ix_search_logs_user_hash"), "search_logs", ["user_hash"], unique=False)
    op.create_index(op.f("ix_search_logs_query_hash"), "search_logs", ["query_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_search_logs_query_hash"), table_name="search_logs")
    op.drop_index(op.f("ix_search_logs_user_hash"), table_name="search_logs")
    op.drop_index(op.f("ix_search_logs_source"), table_name="search_logs")
    op.drop_index(op.f("ix_search_logs_created_at"), table_name="search_logs")
    op.drop_table("search_logs")
