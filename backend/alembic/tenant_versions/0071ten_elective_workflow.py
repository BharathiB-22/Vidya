"""tenant: elective offering workflow (Faculty proposes, Dean approves, Admin publishes)

Revision ID: 0071ten
Revises: 0070ten
Create Date: 2026-07-06

elective_offerings previously only supported OPEN/CLOSED, created directly by
ADMIN/DEAN (status column was String(10)). This migration widens the status
column (DEAN_APPROVED is 13 chars) and adds the workflow columns needed for
the new propose -> approve/reject -> publish lifecycle. Fully additive: the
existing direct-create path (status defaults to OPEN) is unaffected.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0071ten"
down_revision = "0070ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.alter_column(
        "elective_offerings", "status",
        type_=sa.String(20),
        existing_type=sa.String(10),
        existing_nullable=False,
    )
    op.add_column("elective_offerings", sa.Column("proposed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("elective_offerings", sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("elective_offerings", sa.Column("approved_at",         sa.DateTime(timezone=True),    nullable=True))
    op.add_column("elective_offerings", sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("elective_offerings", sa.Column("published_at",        sa.DateTime(timezone=True),    nullable=True))
    op.add_column("elective_offerings", sa.Column("rejection_reason",    sa.Text(),                      nullable=True))


def downgrade() -> None:
    op.drop_column("elective_offerings", "rejection_reason")
    op.drop_column("elective_offerings", "published_at")
    op.drop_column("elective_offerings", "published_by_user_id")
    op.drop_column("elective_offerings", "approved_at")
    op.drop_column("elective_offerings", "approved_by_user_id")
    op.drop_column("elective_offerings", "proposed_by_user_id")
    op.alter_column(
        "elective_offerings", "status",
        type_=sa.String(10),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
