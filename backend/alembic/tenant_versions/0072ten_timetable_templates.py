"""tenant: create timetable_templates & timetable_periods (Phase 4.1)

Revision ID: 0072ten
Revises: 0071ten
Create Date: 2026-07-06

Tables created (tenant schema):
  timetable_templates — department-owned schedule shape (working days,
                         Saturday mode, college hours).
  timetable_periods   — ordered period/break sequence belonging to one
                         template. period_number is unique per template
                         among non-null values (breaks have no period_number).

Also adds a nullable timetables.template_id FK (SET NULL on delete) so a
pre-existing Phase-4 timetable with no template keeps working unchanged —
fully additive, no existing behavior touched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0072ten"
down_revision = "0071ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "timetable_templates",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("department_id",        postgresql.UUID(as_uuid=True), sa.ForeignKey("acad_departments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name",                 sa.String(),                   nullable=False),
        sa.Column("working_days",         postgresql.JSONB(),            nullable=False),
        sa.Column("saturday_mode",        sa.String(10),                 nullable=True),
        sa.Column("college_start_time",   sa.Time(),                     nullable=False),
        sa.Column("college_end_time",     sa.Time(),                     nullable=False),
        sa.Column("created_by_user_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",           sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_timetable_templates_department_id", "timetable_templates", ["department_id"])

    op.create_table(
        "timetable_periods",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("template_id",      postgresql.UUID(as_uuid=True), sa.ForeignKey("timetable_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_number",  sa.Integer(),                  nullable=False),
        sa.Column("period_type",      sa.String(10),                 nullable=False),
        sa.Column("period_number",    sa.Integer(),                  nullable=True),
        sa.Column("label",            sa.String(50),                 nullable=True),
        sa.Column("start_time",       sa.Time(),                     nullable=False),
        sa.Column("end_time",         sa.Time(),                     nullable=False),
        sa.Column("skip_on_half_day", sa.Boolean(),                  nullable=False, server_default=sa.text("false")),
        sa.Column("created_at",       sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("template_id", "sequence_number", name="uq_timetable_period_sequence"),
    )
    op.create_index("ix_timetable_periods_template_id", "timetable_periods", ["template_id"])
    # Partial unique index: only non-null period_number values must be unique
    # per template (BREAK rows have period_number=NULL and are unrestricted).
    op.create_index(
        "uq_timetable_periods_template_period_number",
        "timetable_periods",
        ["template_id", "period_number"],
        unique=True,
        postgresql_where=sa.text("period_number IS NOT NULL"),
    )

    op.add_column(
        "timetables",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("timetable_templates.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_timetables_template_id", "timetables", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_timetables_template_id", table_name="timetables")
    op.drop_column("timetables", "template_id")

    op.drop_index("uq_timetable_periods_template_period_number", table_name="timetable_periods")
    op.drop_index("ix_timetable_periods_template_id", table_name="timetable_periods")
    op.drop_table("timetable_periods")

    op.drop_index("ix_timetable_templates_department_id", table_name="timetable_templates")
    op.drop_table("timetable_templates")
