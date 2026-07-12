"""tenant: university-style curriculum governance — Phase A V2

Revision ID: 0084ten
Revises: 0083ten
Create Date: 2026-07-12

What V2 changes about V1
------------------------
V1 gave the governance authority a REVIEW role: it could approve a curriculum or
send it back to the Dean. V2 makes it the academic OWNER: it cannot send work
back, because there is nowhere to send it. When the Board finds the curriculum
wanting it enhances the curriculum itself — rearranging semesters, improving
subject flow, adjusting credits, refining elective baskets — then generates the
official syllabus, approves, and locks. The Dean plans and publishes.

    Dean drafts -> submits -> [Dean read-only, permanently]
                              Board edits structure
                              Board generates official syllabus
                              Board edits + approves syllabus
                              Board approves  -> LOCKED (structure AND syllabus)
                              Dean notified -> Dean publishes

There is no return, no reject, no request-changes, and no reopen. Approval is the
only freeze and it is permanent: a later academic change is a NEW curriculum
version created by the Dean.

Summary of changes
------------------

ALTER programs
    + academic_year                  VARCHAR(9)   NULL  -- '2026-2028'
    + structure_finalized_at         TIMESTAMPTZ  NULL  -- stamped automatically by
    + structure_finalized_by_user_id UUID         NULL  -- the first syllabus generation

    status: RETURNED -> DRAFT (data migration; the value is retired)

CREATE UNIQUE INDEX uq_programs_curriculum_version
    (acad_program_id, effective_from_batch_id, version) WHERE both are set.
    A published curriculum is identified by Program + Batch + Version — "MCA,
    2026-2028, v1". Legacy rows have NULLs and the partial index ignores them,
    so nothing existing can collide.

ALTER syllabi
    + objectives           JSONB NOT NULL DEFAULT '[]'  -- Course Objectives, distinct from Outcomes
    + practical_components JSONB NOT NULL DEFAULT '[]'  -- for Lab courses / P > 0
    dean_comment -> board_comment                       -- the Board owns this now, not the Dean

    status: six values collapse to four. The Board authors AND approves the
    syllabus, so a submit/review handoff state is meaningless:

        DRAFT | PENDING_REVIEW | REJECTED -> DRAFT
        DEAN_APPROVED                     -> APPROVED
        DEAN_LOCKED                       -> LOCKED
        AI_GENERATING                     -> unchanged

    created_by_user_id is deliberately left alone on legacy faculty-authored
    syllabi — that is historical truth. Edit rights move to the Board regardless.

ALTER elective_baskets
    + locked_at         TIMESTAMPTZ NULL
    + locked_by_user_id UUID        NULL
    Basket COMPOSITION (which subjects Elective 1 offers) freezes at curriculum
    approval. This is a different axis from ElectiveSlotStatus, which governs
    student REGISTRATION (DRAFT/PUBLISHED/OPEN/CLOSED) and is untouched.

No new tables. Board changes are tracked in the existing append-only audit log.

Grandfathering
--------------
Existing published curricula are NOT modified and NOT invalidated. They predate
the syllabus-completeness gate and may legitimately have zero syllabi; they keep
working exactly as they do today. The gate applies to approvals from here on,
never retroactively.

Courses are untouched: Category (Core/Elective/Lab/Project) and Contact Hours are
DERIVED at read time from columns that already exist (is_elective, course_type,
hours_lecture/tutorial/practical). The Dean's course form gains no new field, and
a derived value cannot drift from the curriculum the way a stored copy would.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision      = "0084ten"
down_revision = "0083ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ---- programs: batch-bound versioning + internal structure marker --------
    op.add_column("programs", sa.Column("academic_year", sa.String(9), nullable=True))
    op.add_column(
        "programs",
        sa.Column("structure_finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "programs",
        sa.Column("structure_finalized_by_user_id", UUID(as_uuid=True), nullable=True),
    )

    # RETURNED is retired — the Board never sends a curriculum back. Any program
    # sitting in it goes back to the Dean's DRAFT, which is where a returned
    # curriculum functionally was anyway (Dean-owned and editable).
    op.execute("UPDATE programs SET status = 'DRAFT' WHERE status = 'RETURNED'")

    # A curriculum version is identified by (program, batch, version). Partial:
    # legacy rows without an acad_program_id or a batch are exempt.
    op.create_index(
        "uq_programs_curriculum_version",
        "programs",
        ["acad_program_id", "effective_from_batch_id", "version"],
        unique=True,
        postgresql_where=sa.text(
            "acad_program_id IS NOT NULL AND effective_from_batch_id IS NOT NULL"
        ),
    )

    # ---- syllabi: official university format ---------------------------------
    op.add_column(
        "syllabi",
        sa.Column(
            "objectives", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.add_column(
        "syllabi",
        sa.Column(
            "practical_components",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("syllabi", "dean_comment", new_column_name="board_comment")

    # ---- syllabi: collapse the lifecycle -------------------------------------
    op.execute(
        "UPDATE syllabi SET status = 'DRAFT' "
        "WHERE status IN ('PENDING_REVIEW', 'REJECTED')"
    )
    op.execute("UPDATE syllabi SET status = 'APPROVED' WHERE status = 'DEAN_APPROVED'")
    op.execute("UPDATE syllabi SET status = 'LOCKED'   WHERE status = 'DEAN_LOCKED'")

    # ---- elective_baskets: composition freezes at curriculum approval --------
    op.add_column(
        "elective_baskets",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "elective_baskets",
        sa.Column("locked_by_user_id", UUID(as_uuid=True), nullable=True),
    )
    # Baskets of an already-approved curriculum are already conceptually frozen —
    # record that, so the "no new electives after lock" guard reads consistently
    # for curricula approved before this migration.
    op.execute(
        "UPDATE elective_baskets eb "
        "SET locked_at = p.locked_at, locked_by_user_id = p.locked_by_user_id "
        "FROM programs p "
        "WHERE p.id = eb.program_id "
        "  AND p.status IN ('APPROVED', 'PUBLISHED') "
        "  AND p.locked_at IS NOT NULL"
    )


def downgrade() -> None:
    """Restores the columns, but NOT the collapsed status values.

    'DRAFT' cannot be told apart from a syllabus that was PENDING_REVIEW or
    REJECTED before the upgrade, and a program moved off RETURNED cannot be told
    apart from one that was always a DRAFT. Those distinctions are gone. The
    downgrade leaves every row in its collapsed state, which is valid under the
    old enums (DRAFT existed there too) — it just isn't the original value.
    """
    op.execute("UPDATE syllabi SET status = 'DEAN_LOCKED'   WHERE status = 'LOCKED'")
    op.execute("UPDATE syllabi SET status = 'DEAN_APPROVED' WHERE status = 'APPROVED'")

    op.drop_column("elective_baskets", "locked_by_user_id")
    op.drop_column("elective_baskets", "locked_at")

    op.alter_column("syllabi", "board_comment", new_column_name="dean_comment")
    op.drop_column("syllabi", "practical_components")
    op.drop_column("syllabi", "objectives")

    op.drop_index("uq_programs_curriculum_version", table_name="programs")
    op.drop_column("programs", "structure_finalized_by_user_id")
    op.drop_column("programs", "structure_finalized_at")
    op.drop_column("programs", "academic_year")
