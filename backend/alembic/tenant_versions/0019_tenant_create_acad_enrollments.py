"""tenant: create acad_enrollments table

Revision ID: 0019ten
Revises: 0018ten
Create Date: 2026-05-27

One enrollment per student (UNIQUE student_id). ON DELETE CASCADE on student
so removing a user cleans up their placement. Section deletion is RESTRICT —
must re-enroll students before removing a section.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0019ten"
down_revision = "0018ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "acad_enrollments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("student_id",  UUID(as_uuid=True), nullable=False),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("acad_sections.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "enrolled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("student_id", name="uq_acad_enrollments_student_id"),
    )
    op.create_index("ix_acad_enrollments_section_id", "acad_enrollments", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_acad_enrollments_section_id", table_name="acad_enrollments")
    op.drop_table("acad_enrollments")
