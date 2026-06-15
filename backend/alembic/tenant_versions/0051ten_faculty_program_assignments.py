"""Faculty ↔ program assignments — many-to-many program teaching scope.

Phase 1 / Step 3 of the Intelligent ERP Onboarding programme.

Soft-revoke only (rows never deleted).  A partial-unique index enforces at most
one ACTIVE assignment per (faculty_user_id, program_id), while permitting
historical revoked rows and re-assignment after revocation.

Revision ID: 0051ten
Revises: 0050ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0051ten"
down_revision = "0050ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "faculty_program_assignments",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("faculty_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id",        ondelete="CASCADE"), nullable=False),
        sa.Column("program_id",      postgresql.UUID(as_uuid=True), sa.ForeignKey("acad_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active",       sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("assigned_by",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_by",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at",      sa.DateTime(timezone=True), nullable=True),
    )
    # At most one ACTIVE assignment per (faculty, program); revoked rows are exempt.
    op.create_index(
        "uq_fpa_active_faculty_program",
        "faculty_program_assignments",
        ["faculty_user_id", "program_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index("ix_fpa_program",        "faculty_program_assignments", ["program_id"])
    op.create_index("ix_fpa_faculty_active", "faculty_program_assignments", ["faculty_user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_fpa_faculty_active", table_name="faculty_program_assignments")
    op.drop_index("ix_fpa_program",        table_name="faculty_program_assignments")
    op.drop_index("uq_fpa_active_faculty_program", table_name="faculty_program_assignments")
    op.drop_table("faculty_program_assignments")
