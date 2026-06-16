"""Add personal_email + institution_email to users.

Phase 1.2 / Task C — Institution Email Foundation (generation only).

- personal_email     — the member's personal address (retained; backfilled
                       from the existing `email` column).
- institution_email  — the generated institutional address
                       ({usn|employee_id}@{tenant institution_domain}).
                       Unique within the tenant schema (multiple NULLs allowed).

The existing `email` column (used for login) is left untouched.  No login
migration is performed here.

Revision ID: 0053ten
Revises: 0052ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "0053ten"
down_revision = "0052ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("users", sa.Column("personal_email", sa.String(), nullable=True))
    op.add_column("users", sa.Column("institution_email", sa.String(), nullable=True))
    # Unique per tenant (each tenant is its own schema). Postgres permits
    # multiple NULLs under a UNIQUE index, so un-backfilled users don't clash.
    op.create_index(
        "uq_users_institution_email",
        "users",
        ["institution_email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_institution_email", table_name="users")
    op.drop_column("users", "institution_email")
    op.drop_column("users", "personal_email")
