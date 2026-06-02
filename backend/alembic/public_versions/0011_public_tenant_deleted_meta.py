"""public: add deleted_at and deleted_by_user_id to tenants

Revision ID: 0011pub
Revises: 0010pub
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0011pub"
down_revision = "0010pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "tenants",
        sa.Column("deleted_by_user_id", UUID(as_uuid=True), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "deleted_by_user_id", schema="public")
    op.drop_column("tenants", "deleted_at", schema="public")
