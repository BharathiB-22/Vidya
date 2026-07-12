"""tenant: curriculum governance — Phase A (Academic Governance V1)

Revision ID: 0083ten
Revises: 0082ten
Create Date: 2026-07-11

Summary of changes
------------------

ALTER programs
    + submitted_by_user_id     UUID          NULL   -- Dean who submitted for approval
    + submitted_at             TIMESTAMPTZ   NULL
    + locked_by_user_id        UUID          NULL   -- governance member who locked it
    + locked_at                TIMESTAMPTZ   NULL
    + review_comment           TEXT          NULL   -- last governance return/approve note
    + regulation_year          INTEGER       NULL   -- e.g. 2026 (the "R2026" scheme)
    + effective_from_batch_id  UUID          NULL   -- FK acad_batches; first batch bound to it

CREATE curriculum_approval_requests
    One row per submit → decide cycle. Append-only history: a returned program
    that is resubmitted gets a NEW row with cycle = previous + 1. Nothing is
    ever updated except the decision fields on the open row.

Ownership change this migration exists to support
-------------------------------------------------
Before: the Dean created, approved AND published curriculum — the approval gate
existed but the same human passed it. After: the Dean *prepares* curriculum and
submits it; the governance authority (Board / University Members) reviews,
modifies, approves and LOCKS it; only then does the Dean publish. The locked_*
columns record who froze the curriculum, which the Dean can no longer edit.

`programs.status` gains a RETURNED value (stored as a plain string — the enum is
native_enum=False), used when governance sends a curriculum back to the Dean
with comments. No data migration is needed: no existing row can hold it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0083ten"
down_revision = "0082ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ---- programs: submission / lock / regulation columns -------------------
    op.add_column("programs", sa.Column("submitted_by_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("programs", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("programs", sa.Column("locked_by_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("programs", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("programs", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("programs", sa.Column("regulation_year", sa.Integer(), nullable=True))
    op.add_column(
        "programs",
        sa.Column("effective_from_batch_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_programs_effective_from_batch",
        "programs",
        "acad_batches",
        ["effective_from_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- curriculum_approval_requests ---------------------------------------
    op.create_table(
        "curriculum_approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "program_id",
            UUID(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 1 for the first submission, 2 after one return+resubmit, and so on.
        sa.Column("cycle", sa.Integer(), nullable=False, server_default=sa.text("1")),
        # PENDING → APPROVED | RETURNED. Never leaves a terminal state.
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("submitted_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("submission_note", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_car_program", "curriculum_approval_requests", ["program_id"])
    op.create_index("ix_car_status", "curriculum_approval_requests", ["status"])
    op.create_unique_constraint(
        "uq_car_program_cycle", "curriculum_approval_requests", ["program_id", "cycle"],
    )
    # At most ONE open request per program: a curriculum cannot be in front of
    # the governance authority twice at the same time.
    op.create_index(
        "uq_car_one_open_per_program",
        "curriculum_approval_requests",
        ["program_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_car_one_open_per_program", table_name="curriculum_approval_requests")
    op.drop_constraint("uq_car_program_cycle", "curriculum_approval_requests", type_="unique")
    op.drop_index("ix_car_status", table_name="curriculum_approval_requests")
    op.drop_index("ix_car_program", table_name="curriculum_approval_requests")
    op.drop_table("curriculum_approval_requests")

    op.drop_constraint("fk_programs_effective_from_batch", "programs", type_="foreignkey")
    for col in (
        "effective_from_batch_id",
        "regulation_year",
        "review_comment",
        "locked_at",
        "locked_by_user_id",
        "submitted_at",
        "submitted_by_user_id",
    ):
        op.drop_column("programs", col)
