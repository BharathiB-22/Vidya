"""tenant: create notifications table

Revision ID: 0003ten
Revises: 0002ten
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003ten"
down_revision = "0002ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id",                postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(),  nullable=False),
        sa.Column("title",             sa.String(),  nullable=False),
        sa.Column("body",              sa.Text(),    nullable=False),
        sa.Column("entity_type",       sa.String(),  nullable=True),
        sa.Column("entity_id",         sa.String(),  nullable=True),
        sa.Column("is_read",           sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_recipient_created", "notifications",
                    ["recipient_user_id", "created_at"])
    op.create_index("ix_notifications_recipient_is_read", "notifications",
                    ["recipient_user_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_is_read",  table_name="notifications")
    op.drop_index("ix_notifications_recipient_created",  table_name="notifications")
    op.drop_table("notifications")
