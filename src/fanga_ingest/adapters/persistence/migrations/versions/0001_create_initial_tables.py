"""create initial tables

Revision ID: 0001
Revises:
Create Date: 2026-10-01 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cabinets",
        sa.Column("cabinet_id", sa.String(), primary_key=True),
        sa.Column("online", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "batteries",
        sa.Column("serial", sa.String(), primary_key=True),
        sa.Column("in_inventory", sa.Boolean(), nullable=False),
        sa.Column("faulted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_batteries_faulted", "batteries", ["faulted"])
    op.create_index("ix_batteries_in_inventory", "batteries", ["in_inventory"])

    op.create_table(
        "observations",
        sa.Column("dedup_key", sa.Text(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_published_at", "outbox", ["published_at"])

    op.create_table(
        "inventory",
        sa.Column("serial", sa.String(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inventory")
    op.drop_table("outbox")
    op.drop_table("observations")
    op.drop_table("batteries")
    op.drop_table("cabinets")
