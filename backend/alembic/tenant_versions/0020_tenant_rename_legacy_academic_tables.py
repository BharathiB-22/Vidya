"""tenant: rename old onboarding academic tables to _legacy_*

Revision ID: 0020ten
Revises: 0019ten
Create Date: 2026-05-27

academic_departments  →  _legacy_academic_departments
academic_programs     →  _legacy_academic_programs

Master data is now owned exclusively by the acad_* hierarchy.
Data is preserved — nothing is dropped.
"""

from alembic import op

revision      = "0020ten"
down_revision = "0019ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.rename_table("academic_departments", "_legacy_academic_departments")
    op.rename_table("academic_programs",    "_legacy_academic_programs")


def downgrade() -> None:
    op.rename_table("_legacy_academic_programs",    "academic_programs")
    op.rename_table("_legacy_academic_departments", "academic_departments")
