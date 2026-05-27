"""tenant: add acad_program_id reference to programs table

Revision ID: 0021ten
Revises: 0020ten
Create Date: 2026-05-27

Adds an optional FK from m01 programs → acad_programs.
ON DELETE SET NULL: deleting an AcadProgram nulls the reference here.
No existing rows are modified. Fully backward-compatible.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0021ten"
down_revision = "0020ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column(
            "acad_program_id",
            UUID(as_uuid=True),
            sa.ForeignKey("acad_programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_programs_acad_program_id", "programs", ["acad_program_id"])


def downgrade() -> None:
    op.drop_index("ix_programs_acad_program_id", table_name="programs")
    op.drop_column("programs", "acad_program_id")
