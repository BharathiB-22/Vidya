"""Repair governance role consistency — promote legacy FACULTY+grant accounts to
proper BOARD/DEAN primary roles and bootstrap Faculty Directory visibility.

Three idempotent steps run for every tenant on ``alembic upgrade head``:

1. FACULTY users with an active BOARD grant  → role = BOARD
2. FACULTY users with an active DEAN  grant  → role = DEAN
3. Revoke the now-redundant governance grants for the promoted users
4. Create minimal sis_faculty_profiles stubs for BOARD/DEAN users that lack one
   (enables Faculty Directory listing and department filter via primary_department_id).

This supersedes the manual ``scripts/repair_board_dean_roles.py`` used in P1.8.2.
New tenants run this migration during provisioning so they never need a separate
repair step.

Revision ID: 0056ten
Revises:     0055ten
"""
from __future__ import annotations

from alembic import op

revision      = "0056ten"
down_revision = "0055ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Step 1: Promote FACULTY + active BOARD grant → primary role BOARD
    op.execute(
        """
        UPDATE users
        SET    role = CAST('BOARD' AS tenantrole)
        WHERE  role = CAST('FACULTY' AS tenantrole)
          AND  id IN (
                   SELECT faculty_user_id
                   FROM   faculty_role_grants
                   WHERE  role_code = 'BOARD' AND is_active = true
               )
        """
    )

    # Step 2: Promote FACULTY + active DEAN grant → primary role DEAN
    op.execute(
        """
        UPDATE users
        SET    role = CAST('DEAN' AS tenantrole)
        WHERE  role = CAST('FACULTY' AS tenantrole)
          AND  id IN (
                   SELECT faculty_user_id
                   FROM   faculty_role_grants
                   WHERE  role_code = 'DEAN' AND is_active = true
               )
        """
    )

    # Step 3: Revoke governance grants whose primary role has now been set.
    # Revoked_by is left NULL (system-initiated repair, no actor user).
    op.execute(
        """
        UPDATE faculty_role_grants
        SET    is_active  = false,
               revoked_at = now(),
               updated_at = now()
        WHERE  role_code IN ('BOARD', 'DEAN')
          AND  is_active  = true
          AND  faculty_user_id IN (
                   SELECT id FROM users
                   WHERE  role IN (
                              CAST('BOARD' AS tenantrole),
                              CAST('DEAN'  AS tenantrole)
                          )
               )
        """
    )

    # Step 4: Create stub sis_faculty_profiles for BOARD/DEAN users who have none.
    # lifecycle_status defaults to 'ACTIVE' via the column server_default (0041ten).
    # employee_id is nullable since 0055ten; the unique constraint allows multiple NULLs.
    op.execute(
        """
        INSERT INTO sis_faculty_profiles (user_id, is_active)
        SELECT u.id, true
        FROM   users u
        LEFT   JOIN sis_faculty_profiles p ON p.user_id = u.id
        WHERE  u.role IN (
                   CAST('BOARD' AS tenantrole),
                   CAST('DEAN'  AS tenantrole)
               )
          AND  p.user_id IS NULL
        ON CONFLICT (user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Role promotion cannot be safely reversed: the grant rows were soft-revoked
    # and the original FACULTY role cannot be restored without the original import
    # data.  This is intentional — the repair is a one-way state correction.
    pass
