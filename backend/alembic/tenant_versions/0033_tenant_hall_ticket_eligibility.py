"""0033 – SIS H58: create sis_hall_ticket_batches and sis_hall_ticket_eligibility

Two new tables supporting the hall-ticket eligibility workflow.

Workflow baked into schema:
  1. compute  → rows created/updated with publish_status='DRAFT'
  2. (Dean reviews, overrides individual rows as needed)
  3. publish  → DRAFT rows move to PUBLISHED for the semester
  4. Students can only see PUBLISHED rows
  5. generate batch → only after PUBLISHED; assigns hall_ticket_number

Status lifecycle on eligibility rows:
  ELIGIBLE | NOT_ELIGIBLE | CONDITIONAL

publish_status lifecycle:
  DRAFT → PUBLISHED  (no rollback; override applies to either state)

Hall ticket number format: TOCS-{year}S{sem_number}-{USN}
  Stored on individual eligibility rows, assigned at batch generation.

No changes to existing tables.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision      = "0033ten"
down_revision = "0032ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Table 1: sis_hall_ticket_batches
    # ------------------------------------------------------------------
    op.create_table(
        "sis_hall_ticket_batches",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True),
        sa.Column("semester_id",    UUID(as_uuid=True),
                  sa.ForeignKey("acad_semesters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("scope",          sa.String(10),  nullable=False, server_default="ALL"),
        sa.Column("scope_ref_id",   UUID(as_uuid=True), nullable=True),   # section_id when scope=SECTION
        sa.Column("generated_by",   UUID(as_uuid=True), nullable=False),  # plain UUID — codebase pattern
        sa.Column("generated_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ticket_count",   sa.Integer,     nullable=False, server_default="0"),
        sa.Column("ticket_prefix",  sa.String(40),  nullable=False),      # e.g. TOCS-2026S2
        sa.Column("notes",          sa.Text,        nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ht_batches_semester",      "sis_hall_ticket_batches", ["semester_id"])
    op.create_index("ix_ht_batches_generated_by",  "sis_hall_ticket_batches", ["generated_by"])
    op.create_index("ix_ht_batches_generated_at",  "sis_hall_ticket_batches", ["generated_at"])

    # ------------------------------------------------------------------
    # Table 2: sis_hall_ticket_eligibility
    # ------------------------------------------------------------------
    op.create_table(
        "sis_hall_ticket_eligibility",
        sa.Column("id",               UUID(as_uuid=True), primary_key=True),

        # Who + which semester
        sa.Column("student_id",       UUID(as_uuid=True), nullable=False),   # plain UUID
        sa.Column("semester_id",      UUID(as_uuid=True),
                  sa.ForeignKey("acad_semesters.id", ondelete="RESTRICT"), nullable=False),

        # Publish workflow
        sa.Column("publish_status",   sa.String(12), nullable=False, server_default="DRAFT"),

        # Eligibility result
        sa.Column("status",           sa.String(15), nullable=False, server_default="NOT_ELIGIBLE"),

        # When computed
        sa.Column("computed_at",      sa.DateTime(timezone=True), nullable=True),

        # Snapshot metadata
        sa.Column("attendance_threshold_used", sa.Numeric(5, 2), nullable=False, server_default="75.0"),
        sa.Column("computed_academic_year",    sa.String(20),     nullable=False, server_default=""),
        sa.Column("computed_semester_name",    sa.String(100),    nullable=False, server_default=""),

        # Check results
        sa.Column("attendance_pct",    sa.Numeric(5, 2), nullable=True),
        sa.Column("has_shortage",      sa.Boolean,       nullable=False, server_default="false"),
        sa.Column("marks_all_locked",  sa.Boolean,       nullable=False, server_default="false"),
        sa.Column("marks_all_filled",  sa.Boolean,       nullable=False, server_default="false"),
        sa.Column("failure_reasons",   ARRAY(sa.Text),   nullable=True),

        # Override (Dean / Admin human gate)
        sa.Column("override_by",       UUID(as_uuid=True),          nullable=True),
        sa.Column("override_at",       sa.DateTime(timezone=True),  nullable=True),
        sa.Column("override_reason",   sa.Text,                     nullable=True),
        sa.Column("override_status",   sa.String(15),               nullable=True),

        # Hall ticket assignment
        sa.Column("batch_id",             UUID(as_uuid=True),
                  sa.ForeignKey("sis_hall_ticket_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hall_ticket_number",   sa.String(80), nullable=True),

        # Future exam scheduling fields
        sa.Column("exam_session_id",  UUID(as_uuid=True), nullable=True),
        sa.Column("exam_schedule_id", UUID(as_uuid=True), nullable=True),
        sa.Column("exam_center_id",   UUID(as_uuid=True), nullable=True),
        sa.Column("room_number",      sa.String(30),      nullable=True),
        sa.Column("seat_number",      sa.String(30),      nullable=True),

        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=True),
    )

    op.create_unique_constraint(
        "uq_ht_eligibility_student_semester",
        "sis_hall_ticket_eligibility",
        ["student_id", "semester_id"],
    )
    op.create_index("ix_ht_eligibility_student",        "sis_hall_ticket_eligibility", ["student_id"])
    op.create_index("ix_ht_eligibility_semester",       "sis_hall_ticket_eligibility", ["semester_id"])
    op.create_index("ix_ht_eligibility_status",         "sis_hall_ticket_eligibility", ["status"])
    op.create_index("ix_ht_eligibility_publish_status", "sis_hall_ticket_eligibility", ["publish_status"])
    op.create_index("ix_ht_eligibility_batch_id",       "sis_hall_ticket_eligibility", ["batch_id"])
    op.create_index("ix_ht_eligibility_has_shortage",   "sis_hall_ticket_eligibility", ["has_shortage"])


def downgrade() -> None:
    op.drop_index("ix_ht_eligibility_has_shortage",   table_name="sis_hall_ticket_eligibility")
    op.drop_index("ix_ht_eligibility_batch_id",       table_name="sis_hall_ticket_eligibility")
    op.drop_index("ix_ht_eligibility_publish_status", table_name="sis_hall_ticket_eligibility")
    op.drop_index("ix_ht_eligibility_status",         table_name="sis_hall_ticket_eligibility")
    op.drop_index("ix_ht_eligibility_semester",       table_name="sis_hall_ticket_eligibility")
    op.drop_index("ix_ht_eligibility_student",        table_name="sis_hall_ticket_eligibility")
    op.drop_constraint("uq_ht_eligibility_student_semester", "sis_hall_ticket_eligibility", type_="unique")
    op.drop_table("sis_hall_ticket_eligibility")

    op.drop_index("ix_ht_batches_generated_at",  table_name="sis_hall_ticket_batches")
    op.drop_index("ix_ht_batches_generated_by",  table_name="sis_hall_ticket_batches")
    op.drop_index("ix_ht_batches_semester",      table_name="sis_hall_ticket_batches")
    op.drop_table("sis_hall_ticket_batches")
