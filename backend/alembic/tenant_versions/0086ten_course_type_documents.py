"""tenant: course-type intelligence — Phase A V2.3

Revision ID: 0086ten
Revises: 0085ten
Create Date: 2026-07-12

What this fixes
---------------
Every course got a five-unit theory syllabus. Internships got one. Projects got
one. The laboratory got Unit I through Unit V of lectures it does not deliver.

A Board of Studies does not write a syllabus for an internship — it writes
guidelines: duration, evaluation rubric, weekly activities, what the company must
provide, how the report is formatted, how the viva runs. A laboratory gets a lab
manual and an experiment list, not theory units. A major project gets a handbook.

So the course's TYPE now decides which document the Board produces, and this
migration gives the schema the two things that needs.

Summary of changes
------------------

1. courses.course_type — PROJECT splits into MINI_PROJECT and MAJOR_PROJECT

   They are different documents. A mini project is milestones and reviews inside
   one semester; a major project is a proposal, a timeline, a demonstration and a
   viva. One value could not drive both.

   Existing PROJECT rows are split BY TITLE: anything reading "mini" becomes
   MINI_PROJECT, everything else MAJOR_PROJECT. That is a heuristic, and it is the
   honest one — the old data does not record the distinction, and a major project
   is the safer default (its document is the superset; a Board correcting a mini
   project down loses nothing, while the reverse would silently drop the viva and
   the proposal). The column is a VARCHAR, not a native enum, so no type surgery
   is needed.

2. syllabi.doc_type + syllabi.document

   `document` is the JSONB body of every NON-theory official document — the lab
   manual, the internship guidelines, the project handbook, the seminar guidelines.
   Its shape is validated per type in m02/schemas.py (LabDocument,
   InternshipDocument, MiniProjectDocument, MajorProjectDocument, SeminarDocument),
   not by the database.

   JSONB rather than five tables because these documents are read and written whole
   and never queried across: the Board opens one course's handbook, edits its
   rubric, saves it. Five tables would buy nothing and cost every one of them a
   join, a repository and a migration each time an accreditation body adds a field.

   `doc_type` is a SNAPSHOT of the course's type at generation time, and it is
   deliberately not derived from courses.course_type at read time. If a Dean
   reclassifies a course from LAB to THEORY after the Board approved its lab
   manual, the approved document is still a lab manual — the row must keep saying
   so, rather than re-labelling an experiment list as a syllabus.

   Theory syllabi keep units, outcomes and references exactly as they are, and get
   doc_type = 'THEORY' with an empty document. Nothing existing is destroyed.

3. syllabi.dean_edited_at / dean_edited_by_user_id

   The Dean may modify Internship, Mini Project, Major Project and Seminar
   guidelines AFTER Board approval, because they depend on the company, the
   supervisor and institutional policy. A theory syllabus they may not touch.

   That edit happens to an APPROVED, otherwise-immutable row, so it is stamped:
   without this, the Board's approved document and the Dean's adaptation of it are
   indistinguishable in the record, and the governance trail cannot say who wrote
   the rubric a student was marked against.

Backfill of doc_type uses the courses table, so a syllabus written before this
migration is labelled with the type its course actually has.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision      = "0086ten"
down_revision = "0085ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Split PROJECT -> MINI_PROJECT / MAJOR_PROJECT
    # ------------------------------------------------------------------
    op.execute(
        """
        UPDATE courses
           SET course_type = CASE
                 WHEN title ILIKE '%mini%' THEN 'MINI_PROJECT'
                 ELSE 'MAJOR_PROJECT'
               END
         WHERE course_type = 'PROJECT'
        """
    )

    # ------------------------------------------------------------------
    # 2. The type-specific official document
    # ------------------------------------------------------------------
    op.add_column("syllabi", sa.Column("doc_type", sa.String(20), nullable=True))
    op.add_column(
        "syllabi",
        sa.Column(
            "document",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Label every existing syllabus with its course's type. Courses that never had
    # a type recorded read as THEORY — which is what they were generated as, and
    # what their units contain.
    op.execute(
        """
        UPDATE syllabi s
           SET doc_type = COALESCE(c.course_type, 'THEORY')
          FROM courses c
         WHERE c.id = s.course_id
        """
    )
    op.execute("UPDATE syllabi SET doc_type = 'THEORY' WHERE doc_type IS NULL")
    op.alter_column("syllabi", "doc_type", nullable=False)

    op.create_index("ix_syllabi_doc_type", "syllabi", ["doc_type"])

    # ------------------------------------------------------------------
    # 3. Dean's post-approval adaptation of guideline documents
    # ------------------------------------------------------------------
    op.add_column(
        "syllabi",
        sa.Column("dean_edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "syllabi",
        sa.Column("dean_edited_by_user_id", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("syllabi", "dean_edited_by_user_id")
    op.drop_column("syllabi", "dean_edited_at")
    op.drop_index("ix_syllabi_doc_type", table_name="syllabi")
    op.drop_column("syllabi", "document")
    op.drop_column("syllabi", "doc_type")

    # Both project types fold back to the single PROJECT value they came from.
    op.execute(
        """
        UPDATE courses
           SET course_type = 'PROJECT'
         WHERE course_type IN ('MINI_PROJECT', 'MAJOR_PROJECT')
        """
    )
