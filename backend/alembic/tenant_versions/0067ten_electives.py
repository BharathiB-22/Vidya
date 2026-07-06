"""tenant: create elective_offerings & elective_registrations tables

Revision ID: 0067ten
Revises: 0066ten
Create Date: 2026-07-06

Course.is_elective (m01_program_advisor) only tags a course as an elective
slot type at curriculum-design time; there was no seat/offering/registration
workflow anywhere before this migration.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0067ten"
down_revision = "0066ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "elective_offerings",
        sa.Column("id",                      postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id",                postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("faculty_user_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("max_seats",                sa.Integer(),                  nullable=False),
        sa.Column("registration_opens_at",    sa.DateTime(timezone=True),    nullable=True),
        sa.Column("registration_closes_at",   sa.DateTime(timezone=True),    nullable=True),
        sa.Column("status",                   sa.String(10),                 nullable=False, server_default="OPEN"),
        sa.Column("created_by_user_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",               sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",               sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["course_id"],   ["courses.id"],        ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["semester_id"], ["acad_semesters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_elective_offerings_semester", "elective_offerings", ["semester_id"])
    op.create_index("ix_elective_offerings_course",   "elective_offerings", ["course_id"])
    op.create_index("ix_elective_offerings_status",   "elective_offerings", ["status"])

    op.create_table(
        "elective_registrations",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("offering_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("registered_at",   sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("status",          sa.String(10),                 nullable=False, server_default="REGISTERED"),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["offering_id"], ["elective_offerings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("offering_id", "student_user_id", name="uq_elective_registrations_offering_student"),
    )
    op.create_index("ix_elective_registrations_offering", "elective_registrations", ["offering_id"])
    op.create_index("ix_elective_registrations_student",  "elective_registrations", ["student_user_id"])


def downgrade() -> None:
    op.drop_index("ix_elective_registrations_student",  table_name="elective_registrations")
    op.drop_index("ix_elective_registrations_offering",  table_name="elective_registrations")
    op.drop_table("elective_registrations")

    op.drop_index("ix_elective_offerings_status",   table_name="elective_offerings")
    op.drop_index("ix_elective_offerings_course",   table_name="elective_offerings")
    op.drop_index("ix_elective_offerings_semester", table_name="elective_offerings")
    op.drop_table("elective_offerings")
