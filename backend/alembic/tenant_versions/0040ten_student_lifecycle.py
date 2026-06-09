"""Student lifecycle status + history table.

Revision ID: 0040ten
Revises: 0039ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0040ten"
down_revision = "0039ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # Add lifecycle_status to sis_student_profiles (default ACTIVE for existing rows)
    op.add_column(
        "sis_student_profiles",
        sa.Column(
            "lifecycle_status",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.create_index(
        "ix_sis_student_profiles_lifecycle_status",
        "sis_student_profiles",
        ["lifecycle_status"],
    )

    # Lifecycle history — append-only audit trail per student
    op.create_table(
        "sis_student_lifecycle_history",
        sa.Column("id",             postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("student_id",     postgresql.UUID(as_uuid=True), sa.ForeignKey("sis_student_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status",    sa.String(20), nullable=True),   # NULL for initial set
        sa.Column("to_status",      sa.String(20), nullable=False),
        sa.Column("reason",         sa.Text,       nullable=True),
        sa.Column("changed_by",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_sis_slh_student_id",
        "sis_student_lifecycle_history",
        ["student_id"],
    )
    op.create_index(
        "ix_sis_slh_changed_at",
        "sis_student_lifecycle_history",
        ["changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sis_slh_changed_at",   table_name="sis_student_lifecycle_history")
    op.drop_index("ix_sis_slh_student_id",   table_name="sis_student_lifecycle_history")
    op.drop_table("sis_student_lifecycle_history")
    op.drop_index("ix_sis_student_profiles_lifecycle_status", table_name="sis_student_profiles")
    op.drop_column("sis_student_profiles", "lifecycle_status")
