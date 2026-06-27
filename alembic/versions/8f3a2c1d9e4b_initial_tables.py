"""initial tables

Revision ID: 8f3a2c1d9e4b
Revises:
Create Date: 2026-06-27 22:38:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8f3a2c1d9e4b"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("document_id_hash", sa.String(length=64), nullable=True),
        sa.Column("document_id_last4", sa.String(length=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_persons_document_id_hash"), "persons", ["document_id_hash"], unique=False)
    op.create_index(op.f("ix_persons_document_id_last4"), "persons", ["document_id_last4"], unique=False)
    op.create_index(op.f("ix_persons_full_name"), "persons", ["full_name"], unique=False)
    op.create_index(op.f("ix_persons_normalized_name"), "persons", ["normalized_name"], unique=False)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("reliability_level", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "appearances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_appearances_person_id"), "appearances", ["person_id"], unique=False)
    op.create_index(op.f("ix_appearances_source_id"), "appearances", ["source_id"], unique=False)
    op.create_index(op.f("ix_appearances_status"), "appearances", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_appearances_status"), table_name="appearances")
    op.drop_index(op.f("ix_appearances_source_id"), table_name="appearances")
    op.drop_index(op.f("ix_appearances_person_id"), table_name="appearances")
    op.drop_table("appearances")
    op.drop_table("sources")
    op.drop_index(op.f("ix_persons_normalized_name"), table_name="persons")
    op.drop_index(op.f("ix_persons_full_name"), table_name="persons")
    op.drop_index(op.f("ix_persons_document_id_last4"), table_name="persons")
    op.drop_index(op.f("ix_persons_document_id_hash"), table_name="persons")
    op.drop_table("persons")
