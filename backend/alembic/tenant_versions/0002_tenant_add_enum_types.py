"""tenant: add native enum types for role and purpose

Revision ID: 0002ten
Revises: 0001ten
Create Date: 2026-05-06
"""

from alembic import op

revision = "0002ten"
down_revision = "0001ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE tenantrole AS ENUM "
        "('ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE')"
    )
    op.execute("CREATE TYPE otppurpose AS ENUM ('PASSWORD_RESET')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role "
        "TYPE tenantrole USING role::tenantrole"
    )
    op.execute(
        "ALTER TABLE otp_codes ALTER COLUMN purpose "
        "TYPE otppurpose USING purpose::otppurpose"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE otp_codes ALTER COLUMN purpose "
        "TYPE VARCHAR USING purpose::VARCHAR"
    )
    op.execute(
        "ALTER TABLE users ALTER COLUMN role "
        "TYPE VARCHAR USING role::VARCHAR"
    )
    op.execute("DROP TYPE IF EXISTS otppurpose")
    op.execute("DROP TYPE IF EXISTS tenantrole")
