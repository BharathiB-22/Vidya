"""tenant: assignment question builder + question-paper fallback (P1.20)

Revision ID: 0100ten
Revises: 0099ten
Create Date: 2026-07-20

The "New Assignment" page could capture only metadata — title, type, marks, due
date and so on — with no way for the faculty to write down the actual questions,
nor to attach a question paper. This adds exactly those two, both additive and
both on the assignments table:

    assignments.questions            the questions the faculty set, in order, as
                                     a JSONB list of
                                     {question_number, question_text, marks,
                                     notes}. Empty [] = no structured questions.
                                     When non-empty, the marks sum to max_marks
                                     (enforced in the service, not the DB).

    assignments.question_paper_url   S3 object key of an uploaded question paper
                                     (.pdf/.docx), the fallback used when no
                                     structured questions are entered. NULL = none.

Backward compatible: every existing assignment backfills to questions = [] and
question_paper_url = NULL, i.e. "metadata only", which is exactly how they behave
today. Nothing about grading, submission or the evaluation hand-off changes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0100ten"
down_revision = "0099ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column(
            "questions",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "assignments",
        sa.Column("question_paper_url", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assignments", "question_paper_url")
    op.drop_column("assignments", "questions")
