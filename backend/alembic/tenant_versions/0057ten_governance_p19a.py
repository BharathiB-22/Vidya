"""P1.9A — Governance refinement: DEAN profile stubs + department derivation.

Idempotent additive migration.  Safe to run multiple times against any tenant.

Step 1: Create sis_faculty_profiles stubs for DEAN users who have none.
        Mirrors the existing 0056ten BOARD/DEAN stub step but targets DEAN only,
        so future runs after the import change always ensure a profile exists.

Step 2: Derive primary_department_id from the earliest active
        faculty_program_assignment for every FACULTY and DEAN profile where the
        column is currently NULL.  This fixes the Faculty Directory department
        filter for all existing tenants without touching any existing values.

Does NOT:
  * Change any users.role value.
  * Touch BOARD users beyond what 0056ten already did.
  * Assign faculty_code (requires the atomic counter — handled by import/backfill).
  * Remove or modify any existing data.

Revision ID: 0057ten
Revises:     0056ten
"""
from __future__ import annotations

from alembic import op

revision      = "0057ten"
down_revision = "0056ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Step 1: DEAN profile stubs (additive, ON CONFLICT DO NOTHING).
    op.execute(
        """
        INSERT INTO sis_faculty_profiles (user_id, is_active)
        SELECT u.id, true
        FROM   users u
        LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id
        WHERE  u.role = CAST('DEAN' AS tenantrole)
          AND  p.user_id IS NULL
        ON CONFLICT (user_id) DO NOTHING
        """
    )

    # Step 2: Derive primary_department_id from the earliest active
    # faculty_program_assignment for all profiles (FACULTY + DEAN) that still
    # have a NULL department.  Touches only NULL rows — never overwrites.
    op.execute(
        """
        UPDATE sis_faculty_profiles p
        SET    primary_department_id = sub.department_id,
               updated_at            = now()
        FROM (
            SELECT DISTINCT ON (fpa.faculty_user_id)
                   fpa.faculty_user_id,
                   ap.department_id
            FROM   faculty_program_assignments fpa
            JOIN   acad_programs ap ON ap.id = fpa.program_id
            JOIN   users u          ON u.id  = fpa.faculty_user_id
            WHERE  fpa.is_active       = true
              AND  ap.department_id    IS NOT NULL
              AND  u.role IN (
                       CAST('FACULTY' AS tenantrole),
                       CAST('DEAN'    AS tenantrole)
                   )
            ORDER  BY fpa.faculty_user_id, fpa.assigned_at
        ) sub
        WHERE  p.user_id              = sub.faculty_user_id
          AND  p.primary_department_id IS NULL
        """
    )


def downgrade() -> None:
    # Department derivation cannot be safely reversed without knowing which
    # rows were set by this migration vs. prior data.  No-op intentional.
    pass
