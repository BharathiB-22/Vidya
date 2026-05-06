"""public: add status column to tenants

Revision ID: 0002pub
Revises: 0001pub
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0002pub"
down_revision = "0001pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="ACTIVE",
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "status", schema="public")
