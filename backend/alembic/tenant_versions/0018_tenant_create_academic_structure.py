"""tenant: create academic structure tables

Revision ID: 0018ten
Revises: 0017ten
Create Date: 2026-05-27

Creates five acad_* tables that form the institution's academic hierarchy:
  acad_departments → acad_programs → acad_batches → acad_semesters → acad_sections

All tables live in the tenant schema (no schema= arg). Prefix `acad_` chosen to
avoid collision with m01's existing `programs` table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0018ten"
down_revision = "0017ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. Departments
    op.create_table(
        "acad_departments",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True),
        sa.Column("name",        sa.String(),        nullable=False),
        sa.Column("code",        sa.String(10),      nullable=False),
        sa.Column("description", sa.Text(),          nullable=True),
        sa.Column("is_active",   sa.Boolean(),       nullable=False, server_default=sa.true()),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", name="uq_acad_departments_name"),
        sa.UniqueConstraint("code", name="uq_acad_departments_code"),
    )

    # 2. Programs
    op.create_table(
        "acad_programs",
        sa.Column("id",             UUID(as_uuid=True), primary_key=True),
        sa.Column("department_id",  UUID(as_uuid=True), sa.ForeignKey("acad_departments.id"), nullable=False),
        sa.Column("name",           sa.String(),        nullable=False),
        sa.Column("code",           sa.String(10),      nullable=False),
        sa.Column("degree_type",    sa.String(20),      nullable=False),
        sa.Column("duration_years", sa.SmallInteger(),  nullable=False),
        sa.Column("is_active",      sa.Boolean(),       nullable=False, server_default=sa.true()),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code", name="uq_acad_programs_code"),
    )
    op.create_index("ix_acad_programs_department_id", "acad_programs", ["department_id"])

    # 3. Batches
    op.create_table(
        "acad_batches",
        sa.Column("id",         UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", UUID(as_uuid=True), sa.ForeignKey("acad_programs.id"), nullable=False),
        sa.Column("name",       sa.String(),        nullable=False),
        sa.Column("start_year", sa.SmallInteger(),  nullable=False),
        sa.Column("end_year",   sa.SmallInteger(),  nullable=False),
        sa.Column("is_active",  sa.Boolean(),       nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("program_id", "start_year", name="uq_acad_batches_program_start_year"),
    )
    op.create_index("ix_acad_batches_program_id", "acad_batches", ["program_id"])

    # 4. Semesters
    op.create_table(
        "acad_semesters",
        sa.Column("id",         UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id",   UUID(as_uuid=True), sa.ForeignKey("acad_batches.id"), nullable=False),
        sa.Column("number",     sa.SmallInteger(),  nullable=False),
        sa.Column("label",      sa.String(),        nullable=True),
        sa.Column("start_date", sa.Date(),          nullable=True),
        sa.Column("end_date",   sa.Date(),          nullable=True),
        sa.Column("is_active",  sa.Boolean(),       nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("batch_id", "number", name="uq_acad_semesters_batch_number"),
    )
    op.create_index("ix_acad_semesters_batch_id", "acad_semesters", ["batch_id"])

    # 5. Sections
    op.create_table(
        "acad_sections",
        sa.Column("id",           UUID(as_uuid=True), primary_key=True),
        sa.Column("semester_id",  UUID(as_uuid=True), sa.ForeignKey("acad_semesters.id"), nullable=False),
        sa.Column("name",         sa.String(),        nullable=False),
        sa.Column("max_strength", sa.SmallInteger(),  nullable=True),
        sa.Column("is_active",    sa.Boolean(),       nullable=False, server_default=sa.true()),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("semester_id", "name", name="uq_acad_sections_semester_name"),
    )
    op.create_index("ix_acad_sections_semester_id", "acad_sections", ["semester_id"])


def downgrade() -> None:
    op.drop_table("acad_sections")
    op.drop_table("acad_semesters")
    op.drop_table("acad_batches")
    op.drop_table("acad_programs")
    op.drop_table("acad_departments")
