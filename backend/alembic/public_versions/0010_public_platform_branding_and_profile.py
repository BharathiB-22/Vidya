"""public: add avatar_url to platform_users and create platform_branding table

Revision ID: 0010pub
Revises: 0009pub
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0010pub"
down_revision = "0009pub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_users",
        sa.Column("avatar_url", sa.String(500), nullable=True),
        schema="public",
    )

    op.create_table(
        "platform_branding",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform_name", sa.String(100), nullable=False, server_default="VIDYA AI"),
        sa.Column("company_name", sa.String(100), nullable=False, server_default="SherpaVector"),
        sa.Column("support_email", sa.String(255), nullable=True),
        sa.Column("support_phone", sa.String(50), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("favicon_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="public",
    )

    op.execute(
        "INSERT INTO public.platform_branding (platform_name, company_name) "
        "VALUES ('VIDYA AI', 'SherpaVector')"
    )


def downgrade() -> None:
    op.drop_table("platform_branding", schema="public")
    op.drop_column("platform_users", "avatar_url", schema="public")
