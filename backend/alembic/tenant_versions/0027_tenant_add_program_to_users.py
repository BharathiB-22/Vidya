"""tenant: add acad_program_id to users for student program assignment

Revision ID: 0027ten
Revises: 0026ten
Create Date: 2026-05-30

Changes
-------
  users.acad_program_id (UUID, nullable, FK → acad_programs.id SET NULL) —
  stores which academic program a student belongs to. NULL for non-student
  roles (ADMIN, DEAN, FACULTY, BOARD, GUIDE, EVALUATOR). Required at
  creation/update time when role = STUDENT.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0027ten"
down_revision = "0026ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS so this migration is safe to run even when
    # the column was already applied manually via run_migration.py before this
    # revision was formally stamped.
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS acad_program_id UUID "
        "REFERENCES acad_programs(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_acad_program_id "
        "ON users (acad_program_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_users_acad_program_id", table_name="users")
    op.drop_column("users", "acad_program_id")
