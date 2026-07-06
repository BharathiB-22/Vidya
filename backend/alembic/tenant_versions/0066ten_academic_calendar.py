"""tenant: create academic_events table (calendar)

Revision ID: 0066ten
Revises: 0065ten
Create Date: 2026-07-06

Tables created (tenant schema):
  academic_events — admin/dean-declared holidays/events/announcements.
  (Deadline-type calendar items are aggregated at query time from their
  owning modules, not stored here.)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0066ten"
down_revision = "0065ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "academic_events",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title",               sa.String(),                  nullable=False),
        sa.Column("description",         sa.Text(),                    nullable=True),
        sa.Column("event_type",          sa.String(20),                nullable=False, server_default="EVENT"),
        sa.Column("start_at",            sa.DateTime(timezone=True),   nullable=False),
        sa.Column("end_at",              sa.DateTime(timezone=True),   nullable=True),
        sa.Column("is_all_day",          sa.Boolean(),                 nullable=False, server_default="false"),
        sa.Column("visibility",          sa.String(10),                nullable=False, server_default="ALL"),
        sa.Column("program_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_id",            postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",          sa.DateTime(timezone=True),   nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True),   nullable=True),
    )
    op.create_index("ix_academic_events_start_at",   "academic_events", ["start_at"])
    op.create_index("ix_academic_events_visibility",  "academic_events", ["visibility"])
    op.create_index("ix_academic_events_program_id",  "academic_events", ["program_id"])
    op.create_index("ix_academic_events_batch_id",    "academic_events", ["batch_id"])
    op.create_index("ix_academic_events_section_id",  "academic_events", ["section_id"])


def downgrade() -> None:
    op.drop_index("ix_academic_events_section_id",  table_name="academic_events")
    op.drop_index("ix_academic_events_batch_id",    table_name="academic_events")
    op.drop_index("ix_academic_events_program_id",  table_name="academic_events")
    op.drop_index("ix_academic_events_visibility",  table_name="academic_events")
    op.drop_index("ix_academic_events_start_at",    table_name="academic_events")
    op.drop_table("academic_events")
