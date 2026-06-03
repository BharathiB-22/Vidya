"""0032 – SIS H57: create sis_marks_components and sis_marks_entries

Two new tables for subject-wise internal marks management.

Business rules baked into schema:
  - component UNIQUE on (course_id, section_id, name) — same component name
    cannot be repeated within a course+section pair
  - entry UNIQUE on (component_id, student_id) — one mark record per student
    per component; UPSERT is used for bulk saves
  - status lifecycle: DRAFT → PUBLISHED → LOCKED (reopen: LOCKED → PUBLISHED)
  - marks_obtained = NULL means not yet entered (valid state)
  - marks_obtained > max_marks rejected at service layer, not DB constraint
    (to allow advisory display of entered values during validation)
  - semester_id is denormalised on components to avoid deep JOIN chains in
    analytics queries

No changes to existing tables.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0032ten"
down_revision = "0031ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Table 1: sis_marks_components
    # ------------------------------------------------------------------
    op.create_table(
        "sis_marks_components",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True),

        # Context
        sa.Column("course_id",      UUID(as_uuid=True),
                  sa.ForeignKey("courses.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("section_id",     UUID(as_uuid=True),
                  sa.ForeignKey("acad_sections.id",  ondelete="CASCADE"), nullable=False),
        sa.Column("semester_id",    UUID(as_uuid=True),
                  sa.ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by",     UUID(as_uuid=True), nullable=False),  # faculty; plain UUID

        # Definition
        sa.Column("component_type", sa.String(20),        nullable=False),
        sa.Column("name",           sa.String(100),        nullable=False),
        sa.Column("max_marks",      sa.Numeric(6, 2),      nullable=False),
        sa.Column("weightage",      sa.Numeric(5, 2),      nullable=True),
        sa.Column("due_date",       sa.Date,               nullable=True),
        sa.Column("display_order",  sa.SmallInteger,       nullable=True),

        # Lifecycle
        sa.Column("status",         sa.String(12),  nullable=False, server_default="DRAFT"),
        sa.Column("published_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by",      UUID(as_uuid=True),         nullable=True),

        # Reopen
        sa.Column("reopened_by",    UUID(as_uuid=True),          nullable=True),
        sa.Column("reopened_at",    sa.DateTime(timezone=True),  nullable=True),
        sa.Column("reopen_reason",  sa.Text,                     nullable=True),

        sa.Column("is_active",      sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
    )

    op.create_unique_constraint(
        "uq_marks_components_course_section_name",
        "sis_marks_components",
        ["course_id", "section_id", "name"],
    )
    op.create_index("ix_marks_components_course_section", "sis_marks_components", ["course_id",  "section_id"])
    op.create_index("ix_marks_components_section_status", "sis_marks_components", ["section_id", "status"])
    op.create_index("ix_marks_components_semester",       "sis_marks_components", ["semester_id"])
    op.create_index("ix_marks_components_status",         "sis_marks_components", ["status"])
    op.create_index("ix_marks_components_faculty",        "sis_marks_components", ["created_by"])

    # ------------------------------------------------------------------
    # Table 2: sis_marks_entries
    # ------------------------------------------------------------------
    op.create_table(
        "sis_marks_entries",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True),
        sa.Column("component_id",   UUID(as_uuid=True),
                  sa.ForeignKey("sis_marks_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id",     UUID(as_uuid=True), nullable=False),  # plain UUID

        # Mark value
        sa.Column("marks_obtained", sa.Numeric(6, 2), nullable=True),   # NULL = not entered
        sa.Column("remarks",        sa.Text,           nullable=True),

        # First save
        sa.Column("marked_by",      UUID(as_uuid=True),          nullable=True),
        sa.Column("marked_at",      sa.DateTime(timezone=True),  nullable=True),

        # Subsequent edits
        sa.Column("edited_by",      UUID(as_uuid=True),          nullable=True),
        sa.Column("edited_at",      sa.DateTime(timezone=True),  nullable=True),
        sa.Column("edit_reason",    sa.Text,                     nullable=True),

        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
    )

    op.create_unique_constraint(
        "uq_marks_entries_component_student",
        "sis_marks_entries",
        ["component_id", "student_id"],
    )
    op.create_index("ix_marks_entries_component", "sis_marks_entries", ["component_id"])
    op.create_index("ix_marks_entries_student",   "sis_marks_entries", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_marks_entries_student",   table_name="sis_marks_entries")
    op.drop_index("ix_marks_entries_component", table_name="sis_marks_entries")
    op.drop_constraint("uq_marks_entries_component_student", "sis_marks_entries", type_="unique")
    op.drop_table("sis_marks_entries")

    op.drop_index("ix_marks_components_faculty",        table_name="sis_marks_components")
    op.drop_index("ix_marks_components_status",         table_name="sis_marks_components")
    op.drop_index("ix_marks_components_semester",       table_name="sis_marks_components")
    op.drop_index("ix_marks_components_section_status", table_name="sis_marks_components")
    op.drop_index("ix_marks_components_course_section", table_name="sis_marks_components")
    op.drop_constraint("uq_marks_components_course_section_name", "sis_marks_components", type_="unique")
    op.drop_table("sis_marks_components")
