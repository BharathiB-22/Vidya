"""tenant: question definition attributes — units + difficulty (P1.19)

Revision ID: 0097ten
Revises: 0096ten
Create Date: 2026-07-16

The Paper Template is now built from Sections of Question Definitions, and a
definition carries two things a question row could not previously hold:

    exam_questions.unit_numbers   every unit the question draws on. A definition
                                  may pool several units and ask for them to be
                                  INTEGRATED into one question; a single
                                  unit_number cannot say that. unit_number stays
                                  the PRIMARY unit, so unit-coverage reports, the
                                  ix_exam_questions_unit index and every legacy
                                  row keep working untouched.

    exam_questions.difficulty     EASY / MEDIUM / HARD, requested per definition
                                  and honoured by the generator. There was no
                                  difficulty concept in the module before.

Both columns are additive and nullable, so nothing is backfilled and legacy
papers read exactly as they do today (NULL difficulty, NULL unit_numbers → the
question covers unit_number alone).

question_type gains CASE_STUDY and PROGRAMMING. That column is a plain VARCHAR
holding an application-side enum with no CHECK constraint, so the new values need
no schema change — they are listed here only so the change is discoverable from
the migration history.

The template document itself (exam_papers.template_definition, JSONB) moves to
version 3. Older documents are upgraded in memory on read and never rewritten, so
a sealed paper keeps printing exactly what it printed the day it was sealed.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0097ten"
down_revision = "0096ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column(
        "exam_questions",
        sa.Column("unit_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("exam_questions", sa.Column("difficulty", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("exam_questions", "difficulty")
    op.drop_column("exam_questions", "unit_numbers")
