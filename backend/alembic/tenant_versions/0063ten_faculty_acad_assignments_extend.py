"""Extend faculty_program_assignments with full academic scope fields.

Adds:
  department_id  — FK → acad_departments (backfilled from program's department)
  semester_id    — FK → acad_semesters  (optional; null = whole program scope)
  section_id     — FK → acad_sections   (optional; null = all sections)
  is_primary     — boolean; one primary coordinator per program

This upgrade lets a single assignment row capture a faculty member's role at
any level: whole-program (semester/section null), semester-scoped, or
section-scoped.  Existing rows get department_id backfilled from
acad_programs.department_id; is_primary defaults to FALSE.

Safe to run multiple times (IF NOT EXISTS / DO NOTHING guards throughout).
"""
from __future__ import annotations

from alembic import op

revision      = "0063ten"
down_revision = "0062ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Add new columns (idempotent via IF NOT EXISTS)
    op.execute("""
        ALTER TABLE faculty_program_assignments
            ADD COLUMN IF NOT EXISTS department_id UUID
                REFERENCES acad_departments(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS semester_id   UUID
                REFERENCES acad_semesters(id)   ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS section_id    UUID
                REFERENCES acad_sections(id)    ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS is_primary    BOOLEAN NOT NULL DEFAULT FALSE
    """)

    # Backfill department_id from the linked acad_program's department
    op.execute("""
        UPDATE faculty_program_assignments fpa
        SET    department_id = ap.department_id
        FROM   acad_programs ap
        WHERE  ap.id = fpa.program_id
          AND  fpa.department_id IS NULL
    """)

    # Indexes for new FK columns
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fpa_department_id
            ON faculty_program_assignments (department_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_fpa_semester_id
            ON faculty_program_assignments (semester_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fpa_semester_id")
    op.execute("DROP INDEX IF EXISTS ix_fpa_department_id")
    op.execute("""
        ALTER TABLE faculty_program_assignments
            DROP COLUMN IF EXISTS is_primary,
            DROP COLUMN IF EXISTS section_id,
            DROP COLUMN IF EXISTS semester_id,
            DROP COLUMN IF EXISTS department_id
    """)
