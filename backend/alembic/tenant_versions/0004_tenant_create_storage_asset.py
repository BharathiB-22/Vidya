"""tenant: create storage asset table

Revision ID: 0004ten
Revises: 0003ten
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004ten"
down_revision = "0003ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_assets",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("uploaded_by_user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type",          sa.String(),                   nullable=False),
        sa.Column("entity_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_key",           sa.Text(),                     nullable=False),
        sa.Column("original_filename",    sa.String(),                   nullable=False),
        sa.Column("size_bytes",           sa.Integer(),                  nullable=False),
        sa.Column("content_type",         sa.String(),                   nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.Column("deleted_at",           sa.DateTime(timezone=True),    nullable=True),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_storage_assets_entity",             "storage_assets", ["entity_type", "entity_id"])
    op.create_index("ix_storage_assets_uploaded_by_created", "storage_assets", ["uploaded_by_user_id", "created_at"])
    op.create_index("ix_storage_assets_created",            "storage_assets", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_storage_assets_created",             table_name="storage_assets")
    op.drop_index("ix_storage_assets_uploaded_by_created",  table_name="storage_assets")
    op.drop_index("ix_storage_assets_entity",              table_name="storage_assets")
    op.drop_table("storage_assets")
