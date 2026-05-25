"""tenant: add must_change_password column to users

Revision ID: 0014ten
Revises: 0013ten
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0014ten"
down_revision = "0013ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
