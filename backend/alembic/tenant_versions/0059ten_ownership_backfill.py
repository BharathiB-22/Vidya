"""Academic Ownership backfill — dean program scope + faculty profile stubs.

Addresses the production data gap left by 0058ten, which created the
dean_program_assignments table but inserted no rows.

Two idempotent steps:

Step 1 — FACULTY profile stubs
    Create sis_faculty_profiles for any FACULTY user that still lacks one
    (belt-and-suspenders: 0056ten covers BOARD/DEAN; FACULTY stubs are covered
    by the import path but may be absent on hand-created accounts).

Step 2 — Dean program backfill
    For every DEAN user who has a home department (primary_department_id set on
    their sis_faculty_profile) but NO active dean_program_assignments yet,
    insert one row for every active program that belongs to that department.

    Rationale: a DEAN governs their entire home department by default.  Admins
    can later revoke or expand scope via the onboarding UI.

    Idempotency guarantee: the INSERT is gated on NOT EXISTS (active DPAs for
    that dean), so it fires only when the set is completely empty.  Re-running
    after the first backfill is safe — the NOT EXISTS check returns false and
    the INSERT produces zero rows.

Revision ID: 0059ten
Revises:     0058ten
"""
from __future__ import annotations

from alembic import op

revision      = "0059ten"
down_revision = "0058ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Step 1: FACULTY profile stubs
    # Creates a minimal sis_faculty_profiles row for FACULTY users who have
    # none.  Harmless re-run: ON CONFLICT (user_id) DO NOTHING.
    op.execute(
        """
        INSERT INTO sis_faculty_profiles (user_id, is_active)
        SELECT u.id, true
        FROM   users u
        LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id
        WHERE  u.role  = CAST('FACULTY' AS tenantrole)
          AND  p.user_id IS NULL
        ON CONFLICT (user_id) DO NOTHING
        """
    )

    # Step 2: Dean program backfill
    # Only fires for DEANs who have ZERO active dean_program_assignments.
    # If even one active assignment already exists the NOT EXISTS gate blocks
    # the insert entirely — manual scope adjustments are preserved.
    #
    # assigned_by = the dean's own user_id (system repair; no human actor).
    op.execute(
        """
        INSERT INTO dean_program_assignments
               (id, dean_user_id, program_id, is_active, assigned_by, assigned_at)
        SELECT gen_random_uuid(),
               u.id,
               ap.id,
               true,
               u.id,
               now()
        FROM   users u
        JOIN   sis_faculty_profiles fp
                   ON fp.user_id               = u.id
                  AND fp.primary_department_id IS NOT NULL
        JOIN   acad_programs ap
                   ON ap.department_id = fp.primary_department_id
                  AND ap.is_active     = true
        WHERE  u.role = CAST('DEAN' AS tenantrole)
          AND  NOT EXISTS (
                   SELECT 1
                   FROM   dean_program_assignments dpa
                   WHERE  dpa.dean_user_id = u.id
                     AND  dpa.is_active    = true
               )
        """
    )


def downgrade() -> None:
    # Backfilled rows are indistinguishable from admin-assigned rows once live.
    # Rolling back would silently drop legitimate governance assignments.
    # No-op intentional.
    pass
