"""tenant: marks components may belong to an elective group, not a section

Revision ID: 0081ten
Revises: 0080ten
Create Date: 2026-07-10

The mirror of 0080ten, for internal marks. A faculty member teaching an elective
defines ONE "CIE 1" component for the whole elective group and enters marks for
every student who chose that subject — not one component per contributing section.

    section_id IS NOT NULL   a regular course taught to one section
    section_id IS NULL       an elective group: everyone in `semester_id` who
                             registered for `course_id`

Unlike attendance, `sis_marks_components` already denormalises `semester_id`
(NOT NULL since 0032), so nothing needs adding — the term survives the loss of
the section on its own.

As in 0080ten the single unique constraint becomes two partial ones, because a
NULL section_id would otherwise let the same component name be created twice for
one elective group.

Historical rows are NOT rewritten.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0081ten"
down_revision = "0080ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.alter_column("sis_marks_components", "section_id", existing_type=UUID(as_uuid=True), nullable=True)

    op.drop_constraint(
        "uq_marks_components_course_section_name", "sis_marks_components", type_="unique",
    )
    op.create_index(
        "uq_marks_components_section_class", "sis_marks_components",
        ["course_id", "section_id", "name"],
        unique=True, postgresql_where=sa.text("section_id IS NOT NULL"),
    )
    op.create_index(
        "uq_marks_components_elective_class", "sis_marks_components",
        ["course_id", "semester_id", "name"],
        unique=True, postgresql_where=sa.text("section_id IS NULL"),
    )


def downgrade() -> None:
    """Elective-group components have no section to restore. They only exist if
    the tenant ran the new workflow; their entries cascade."""
    op.execute("DELETE FROM sis_marks_components WHERE section_id IS NULL")

    op.drop_index("uq_marks_components_elective_class", table_name="sis_marks_components")
    op.drop_index("uq_marks_components_section_class", table_name="sis_marks_components")
    op.create_unique_constraint(
        "uq_marks_components_course_section_name", "sis_marks_components",
        ["course_id", "section_id", "name"],
    )

    op.alter_column("sis_marks_components", "section_id", existing_type=UUID(as_uuid=True), nullable=False)
