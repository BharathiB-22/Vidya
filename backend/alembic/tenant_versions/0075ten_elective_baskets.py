"""tenant: elective baskets replace single-course electives (Phase 4.2 fix)

Revision ID: 0075ten
Revises: 0074ten
Create Date: 2026-07-08

Architecture fix: an elective was incorrectly modeled as a single Course
flagged is_elective. This introduces `elective_baskets` (a named group of
courses within one program+semester, e.g. "Artificial Intelligence
Electives" containing AI/DL/ML/CV/NLP/...), links `courses.elective_basket_id`
to it, and reworks the m_academics offering/registration tables to operate
on a basket rather than a single course:
  - elective_offerings: course_id + faculty_user_id -> basket_id
    (faculty is no longer meaningful at the offering level now that each
    course inside the basket has its own Course Assignment faculty).
  - elective_registrations: add course_id -- the ONE course the student
    picked from within the open basket.

Early-phase dev branch, no production data — a clean structural fix rather
than a data-preserving migration.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0075ten"
down_revision = "0074ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.create_table(
        "elective_baskets",
        sa.Column("id",                 postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester",           sa.Integer(),                  nullable=False),
        sa.Column("name",               sa.String(),                   nullable=False),
        sa.Column("description",        sa.Text(),                     nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at",         sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",         sa.DateTime(timezone=True),    nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_elective_baskets_program_semester", "elective_baskets", ["program_id", "semester"])

    op.add_column("courses", sa.Column("elective_basket_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_courses_elective_basket", "courses", "elective_baskets",
        ["elective_basket_id"], ["id"], ondelete="SET NULL",
    )

    # elective_offerings: course_id + faculty_user_id -> basket_id
    op.drop_index("ix_elective_offerings_course", table_name="elective_offerings")
    op.drop_constraint("elective_offerings_course_id_fkey", "elective_offerings", type_="foreignkey")
    op.drop_column("elective_offerings", "course_id")
    op.drop_column("elective_offerings", "faculty_user_id")
    op.add_column("elective_offerings", sa.Column("basket_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.create_foreign_key(
        "fk_elective_offerings_basket", "elective_offerings", "elective_baskets",
        ["basket_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_elective_offerings_basket", "elective_offerings", ["basket_id"])

    # elective_registrations: which course within the basket the student picked
    op.add_column("elective_registrations", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.create_foreign_key(
        "fk_elective_registrations_course", "elective_registrations", "courses",
        ["course_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_elective_registrations_course", "elective_registrations", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_elective_registrations_course", table_name="elective_registrations")
    op.drop_constraint("fk_elective_registrations_course", "elective_registrations", type_="foreignkey")
    op.drop_column("elective_registrations", "course_id")

    op.drop_index("ix_elective_offerings_basket", table_name="elective_offerings")
    op.drop_constraint("fk_elective_offerings_basket", "elective_offerings", type_="foreignkey")
    op.drop_column("elective_offerings", "basket_id")
    op.add_column("elective_offerings", sa.Column("faculty_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("elective_offerings", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "elective_offerings_course_id_fkey", "elective_offerings", "courses",
        ["course_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_elective_offerings_course", "elective_offerings", ["course_id"])

    op.drop_constraint("fk_courses_elective_basket", "courses", type_="foreignkey")
    op.drop_column("courses", "elective_basket_id")

    op.drop_index("ix_elective_baskets_program_semester", table_name="elective_baskets")
    op.drop_table("elective_baskets")
