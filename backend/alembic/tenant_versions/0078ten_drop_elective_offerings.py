"""tenant: the elective SLOT is the offering — drop elective_offerings

Revision ID: 0078ten
Revises: 0077ten
Create Date: 2026-07-10

`elective_offerings` existed to bind a curriculum elective slot
(`elective_baskets`, keyed by program + semester NUMBER) to a running term
(`acad_semesters`), and to carry seat caps, a registration window and a
WAITLISTED state. It also forced the Dean to re-declare, in a second screen,
electives they had already defined on the program — two places to create an
elective, two places for it to drift.

Phase 5 removes the duplication. A published program's slot IS the offering:
if the student's current semester number matches the slot's semester, the slot
is registerable. Nothing to open, nothing to close.

Capacity goes with it. Phase 5 has no seat limit — any number of students may
choose the same elective, and everyone who chooses it forms one combined class
across sections. So `max_seats`, `registration_opens_at/closes_at`, the
OPEN/CLOSED status and WAITLISTED all describe constraints that no longer
exist. Re-introducing them later means re-introducing the concept properly,
not reviving these columns.

Registrations are preserved: each row learns the `basket_id` and `semester_id`
its offering used to supply, so a student who has already chosen an elective
keeps that choice. WAITLISTED rows become REGISTERED — with no cap there is
nothing to wait for, and leaving them would hide those students from the
faculty roster.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision      = "0078ten"
down_revision = "0077ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # 1. Give registrations the two facts the offering used to hold for them.
    op.add_column("elective_registrations", sa.Column("basket_id", UUID(as_uuid=True), nullable=True))
    op.add_column("elective_registrations", sa.Column("semester_id", UUID(as_uuid=True), nullable=True))

    op.execute(
        """
        UPDATE elective_registrations er
        SET basket_id = eo.basket_id, semester_id = eo.semester_id
        FROM elective_offerings eo
        WHERE eo.id = er.offering_id
        """
    )

    # A registration whose offering is already gone has no slot to belong to
    # and no semester to be taught in — it cannot be rendered or graded.
    op.execute("DELETE FROM elective_registrations WHERE basket_id IS NULL OR semester_id IS NULL")

    # With no seat cap there is nothing to wait for.
    op.execute("UPDATE elective_registrations SET status = 'REGISTERED' WHERE status = 'WAITLISTED'")

    op.alter_column("elective_registrations", "basket_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.alter_column("elective_registrations", "semester_id", existing_type=UUID(as_uuid=True), nullable=False)

    # 2. Re-key: the student picks one course per SLOT, not per offering.
    op.drop_constraint(
        "uq_elective_registrations_offering_student", "elective_registrations", type_="unique",
    )
    op.drop_index("ix_elective_registrations_offering", table_name="elective_registrations")
    op.drop_column("elective_registrations", "offering_id")

    op.create_foreign_key(
        "fk_elective_registrations_basket", "elective_registrations",
        "elective_baskets", ["basket_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_elective_registrations_semester", "elective_registrations",
        "acad_semesters", ["semester_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_elective_registrations_basket", "elective_registrations", ["basket_id"])
    op.create_index("ix_elective_registrations_semester", "elective_registrations", ["semester_id"])
    op.create_unique_constraint(
        "uq_elective_registrations_basket_student", "elective_registrations",
        ["basket_id", "student_user_id"],
    )

    # 3. The offering itself is now derivable from the published program.
    op.drop_table("elective_offerings")


def downgrade() -> None:
    """Recreates the table and one offering per (basket, semester) that still
    has registrations. Seat caps, registration windows and the propose/approve
    provenance are NOT recoverable — they were dropped, not archived — so
    max_seats is restored as the observed registration count and the workflow
    columns come back empty."""
    op.create_table(
        "elective_offerings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("basket_id", UUID(as_uuid=True), sa.ForeignKey("elective_baskets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semester_id", UUID(as_uuid=True), sa.ForeignKey("acad_semesters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_seats", sa.Integer(), nullable=False),
        sa.Column("registration_opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("proposed_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_elective_offerings_semester", "elective_offerings", ["semester_id"])
    op.create_index("ix_elective_offerings_basket", "elective_offerings", ["basket_id"])
    op.create_index("ix_elective_offerings_status", "elective_offerings", ["status"])

    op.add_column("elective_registrations", sa.Column("offering_id", UUID(as_uuid=True), nullable=True))

    # One offering per distinct (basket, semester) still referenced by a
    # registration. created_by is unknowable; reuse the basket's author.
    op.execute(
        """
        INSERT INTO elective_offerings (id, basket_id, semester_id, max_seats, status, created_by_user_id)
        SELECT gen_random_uuid(), er.basket_id, er.semester_id,
               GREATEST(COUNT(*), 1), 'OPEN', b.created_by_user_id
        FROM elective_registrations er
        JOIN elective_baskets b ON b.id = er.basket_id
        GROUP BY er.basket_id, er.semester_id, b.created_by_user_id
        """
    )
    op.execute(
        """
        UPDATE elective_registrations er
        SET offering_id = eo.id
        FROM elective_offerings eo
        WHERE eo.basket_id = er.basket_id AND eo.semester_id = er.semester_id
        """
    )
    op.execute("DELETE FROM elective_registrations WHERE offering_id IS NULL")
    op.alter_column("elective_registrations", "offering_id", existing_type=UUID(as_uuid=True), nullable=False)

    op.drop_constraint("uq_elective_registrations_basket_student", "elective_registrations", type_="unique")
    op.drop_index("ix_elective_registrations_basket", table_name="elective_registrations")
    op.drop_index("ix_elective_registrations_semester", table_name="elective_registrations")
    op.drop_constraint("fk_elective_registrations_basket", "elective_registrations", type_="foreignkey")
    op.drop_constraint("fk_elective_registrations_semester", "elective_registrations", type_="foreignkey")
    op.drop_column("elective_registrations", "basket_id")
    op.drop_column("elective_registrations", "semester_id")

    op.create_foreign_key(
        "elective_registrations_offering_id_fkey", "elective_registrations",
        "elective_offerings", ["offering_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_elective_registrations_offering", "elective_registrations", ["offering_id"])
    op.create_unique_constraint(
        "uq_elective_registrations_offering_student", "elective_registrations",
        ["offering_id", "student_user_id"],
    )
