"""public: add default_student_password_pattern to tenants — P1.4 Task 6

Revision ID: 0015pub
Revises: 0014pub
Create Date: 2026-06-18

Summary of changes
------------------

ALTER public.tenants
    + default_student_password_pattern  VARCHAR(100)  NULL

Stores the tenant-configured default password pattern for student accounts
(e.g. "Lms@2026", "Vbs@2026").  Foundation only — no login behavior is
changed by this migration.  Future Phase B authentication will consume this.
"""

import sqlalchemy as sa
from alembic import op

revision      = "0015pub"
down_revision = "0014pub"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("default_student_password_pattern", sa.String(100), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("tenants", "default_student_password_pattern", schema="public")
