"""tenant: bind each question to its template block (P1.17)

Revision ID: 0095ten
Revises: 0094ten
Create Date: 2026-07-16

Reconstruction of a paper's template used to be inferred by matching questions to
blocks on (unit_number, marks). That inference is ambiguous — two blocks over the
same unit with the same marks are indistinguishable — and it fails outright when a
generated question's marks/unit drift from the blueprint, which dumped the whole
paper into an "Additional Questions" bucket.

These two additive, nullable columns replace inference with identity:

    exam_questions.template_block_id       the id of the template block (or
                                           compiled blueprint row) the question
                                           belongs to; assigned at generation.
    exam_questions.template_subpart_index  0-based sub-part index within a
                                           FULL_QUESTION block; NULL for sections.

Legacy papers keep NULL and fall back to the previous (unit, marks) matching, so
this is a pure additive change with no backfill.
"""
import sqlalchemy as sa
from alembic import op

revision      = "0095ten"
down_revision = "0094ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("exam_questions", sa.Column("template_block_id", sa.String(), nullable=True))
    op.add_column("exam_questions", sa.Column("template_subpart_index", sa.Integer(), nullable=True))
    op.create_index(
        "ix_exam_questions_template_block",
        "exam_questions",
        ["exam_paper_id", "template_block_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_exam_questions_template_block", table_name="exam_questions")
    op.drop_column("exam_questions", "template_subpart_index")
    op.drop_column("exam_questions", "template_block_id")
