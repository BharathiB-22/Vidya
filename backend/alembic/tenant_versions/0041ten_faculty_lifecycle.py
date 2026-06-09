"""Faculty lifecycle status + history table.

Revision ID: 0041ten
Revises: 0040ten
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "0041ten"
down_revision = "0040ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "sis_faculty_profiles",
        sa.Column(
            "lifecycle_status",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.create_index(
        "ix_sis_faculty_profiles_lifecycle_status",
        "sis_faculty_profiles",
        ["lifecycle_status"],
    )

    op.create_table(
        "sis_faculty_lifecycle_history",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("faculty_id",  postgresql.UUID(as_uuid=True), sa.ForeignKey("sis_faculty_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status",   sa.String(20), nullable=False),
        sa.Column("reason",      sa.Text,       nullable=True),
        sa.Column("changed_by",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("changed_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sis_flh_faculty_id", "sis_faculty_lifecycle_history", ["faculty_id"])
    op.create_index("ix_sis_flh_changed_at", "sis_faculty_lifecycle_history", ["changed_at"])


def downgrade() -> None:
    op.drop_index("ix_sis_flh_changed_at", table_name="sis_faculty_lifecycle_history")
    op.drop_index("ix_sis_flh_faculty_id", table_name="sis_faculty_lifecycle_history")
    op.drop_table("sis_faculty_lifecycle_history")
    op.drop_index("ix_sis_faculty_profiles_lifecycle_status", table_name="sis_faculty_profiles")
    op.drop_column("sis_faculty_profiles", "lifecycle_status")
