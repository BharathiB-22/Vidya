"""Academic Ownership dashboard — create dean_program_assignments table.

Adds the explicit dean ↔ program governance mapping so the Users page
can display program scope for DEAN accounts distinct from the faculty
teaching-scope table (faculty_program_assignments).

Safe to run multiple times (CREATE TABLE IF NOT EXISTS + idempotent indexes).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "0058ten"
down_revision = "0057ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dean_program_assignments (
            id           UUID        NOT NULL DEFAULT gen_random_uuid(),
            dean_user_id UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            program_id   UUID        NOT NULL REFERENCES acad_programs(id) ON DELETE CASCADE,
            is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
            assigned_by  UUID        NOT NULL,
            assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_by   UUID,
            revoked_at   TIMESTAMPTZ,
            CONSTRAINT pk_dean_program_assignments PRIMARY KEY (id)
        )
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dpa_active_dean_program
            ON dean_program_assignments (dean_user_id, program_id)
            WHERE is_active
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_dpa_program
            ON dean_program_assignments (program_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_dpa_dean_active
            ON dean_program_assignments (dean_user_id, is_active)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dean_program_assignments CASCADE")
