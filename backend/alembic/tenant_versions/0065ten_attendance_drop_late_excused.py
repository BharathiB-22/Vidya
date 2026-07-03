"""Attendance: drop LATE/EXCUSED, Present/Absent-only MVP.

Phase 2 refinements: for the Phase 1 MVP, attendance is simplified to two
states — PRESENT and ABSENT. `sis_attendance_records.status` has no DB-level
CHECK constraint or native enum type (it's a plain VARCHAR(10), validated
only at the Pydantic layer), so this migration is a pure data remap with no
DDL beyond that:

  LATE    -> PRESENT  (was counted as attended; stays attended)
  EXCUSED -> ABSENT   (was excluded from both numerator/denominator; since
                        there is no longer a neutral state, it now counts
                        as not-attended)

Applied automatically to every existing tenant via
`app/management/upgrade_all_tenants.py` and to every new tenant via
`app/core/tenants/provisioner.py` — both target alembic "head" dynamically.

Revision ID: 0065ten
Revises: 0064ten
"""
from __future__ import annotations

from alembic import op

revision = "0065ten"
down_revision = "0064ten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE sis_attendance_records SET status = 'PRESENT' WHERE status = 'LATE'")
    op.execute("UPDATE sis_attendance_records SET status = 'ABSENT' WHERE status = 'EXCUSED'")


def downgrade() -> None:
    # Data-lossy: the original LATE vs EXCUSED distinction cannot be
    # recovered from PRESENT/ABSENT alone. No schema change to reverse.
    pass
