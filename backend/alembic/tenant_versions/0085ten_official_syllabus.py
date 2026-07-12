"""tenant: official university syllabus content — Phase A V2

Revision ID: 0085ten
Revises: 0084ten
Create Date: 2026-07-12

What this fixes
---------------
The AI wrote an OUTLINE. A university syllabus is a DOCUMENT.

The unit model could only hold a list of topic objects, so a generated unit came
out as a handful of bullets:

    • Introduction
    • Components

That is not what a Board of Studies publishes. A real regulation reads as a
single flowing block of the concepts the unit covers, in teaching order:

    UNIT I — INTRODUCTION TO COMPUTER SYSTEMS                        (12 Hours)
    Introduction to Computer Systems, Evolution of Computing, Von Neumann
    Architecture, Instruction Cycle, Processor Organization, Memory Hierarchy,
    Cache Memory, Input/Output Organization, Performance Metrics.

Summary of changes
------------------

ALTER syllabus_units
    + content TEXT NULL
        The unit's official prose block — the thing that actually prints. Written
        by the AI, freely rewritten by the Board.

        `topics` is KEPT alongside it, not replaced. It carries the structured
        breakdown (descriptions, sub-concepts, hour estimates) that the course-kit
        generator reads to plan lessons (workers/heavy/course_kit_generation.py
        builds its unit_topics from it). One is the published document, the other
        is the machine-readable scaffolding underneath. Dropping `topics` would
        silently degrade every course kit generated afterwards.

ALTER syllabi
    + internal_assessment JSONB NOT NULL DEFAULT '[]'
        Internal Assessment suggestions — CIE components, weightings, assignment
        patterns. Optional: a course may legitimately have none.

RefType gains WEB_RESOURCE (a code-only change — the column is a VARCHAR, since
the enum is native_enum=False). The bibliography now prints as FOUR sections:

    Text Books        <- TEXTBOOK
    Reference Books   <- REFERENCE, JOURNAL
    Suggested Reading <- SUGGESTED_READING
    Web Resources     <- WEB_RESOURCE, ONLINE

Nothing here is destructive. Existing syllabi keep every unit and every topic;
they simply have no `content` block until the Board regenerates or writes one,
and the document view falls back to rendering their topics.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision      = "0085ten"
down_revision = "0084ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    op.add_column("syllabus_units", sa.Column("content", sa.Text(), nullable=True))
    op.add_column(
        "syllabi",
        sa.Column(
            "internal_assessment",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("syllabi", "internal_assessment")
    op.drop_column("syllabus_units", "content")
