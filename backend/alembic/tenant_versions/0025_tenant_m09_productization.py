"""tenant: M09 productization — scan bundles, quality flags, OCR tracking,
double evaluation config, embedded viewer columns, M08→M09→M10 integration

Revision ID: 0025ten
Revises: 0024ten
Create Date: 2026-05-30

Summary of changes
------------------

NEW TABLE: scanned_script_batches
    Exam bundle workflow — groups scripts uploaded together (one hall, one session).
    exam_paper_id   UUID NOT NULL
    uploaded_by     UUID NOT NULL
    label           VARCHAR NULL        e.g. "Hall A — Afternoon Session"
    file_count      INTEGER DEFAULT 0
    processed_count INTEGER DEFAULT 0
    status          VARCHAR DEFAULT 'PENDING'
                    Values: PENDING / PROCESSING / COMPLETED / PARTIAL / FAILED
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    updated_at      TIMESTAMPTZ NULL

ALTER exam_papers (M08→M09 integration)
    + double_evaluation_enabled  BOOLEAN NOT NULL DEFAULT FALSE
          When true, each scanned_script for this paper requires two independent
          evaluators; discrepancy detection fires automatically after both submit.
    + discrepancy_threshold_pct  NUMERIC(4,1) NULL DEFAULT 20.0
          Delta between primary and secondary evaluator totals (as % of max_marks)
          that triggers a Board escalation flag.

ALTER scanned_scripts
    + ocr_quality_score   NUMERIC(4,2) NULL   overall scan quality 0–100
    + scan_quality_flags  JSONB NULL           [{type, page, severity, description}]
                          type values: BLANK_PAGE / LOW_DPI / ROTATED / DUPLICATE /
                                       PARTIAL_SCAN / MISSING_PAGES
    + batch_id            UUID NULL            FK → scanned_script_batches.id
    + duplicate_of        UUID NULL            advisory link to original if duplicate
                                               detected; no FK constraint (advisory only)
    + page_image_keys     JSONB NULL           [{page_no, s3_key}] per-page images
                                               extracted from PDF for inline viewer (STEP-05)

ALTER script_evaluations (AI enrichment + Board correction)
    + keyword_hits         JSONB NULL   [{keyword, found: bool, context: str}]
    + rubric_mapping       JSONB NULL   [{criterion, max_marks, suggested_marks, justification}]
    + ai_confidence        NUMERIC(4,3) NULL   scorer confidence 0.000–1.000
    + page_range           JSONB NULL   {start_page: int, end_page: int}
    + board_adjusted_marks NUMERIC(5,1) NULL   Board correction of evaluator marks
                           NULL = no adjustment; non-NULL = Board-corrected value
    + board_adjustment_note TEXT NULL   mandatory reason for Board adjustment (enforced at service layer)

ALTER exam_score_ledger (M09→M10 integration)
    + has_board_adjustment BOOLEAN NOT NULL DEFAULT FALSE
          True when any script_evaluation row for this script had board_adjusted_marks set.
          M10 BellCurveAnalysis reads this flag when computing cross-evaluator stats
          to distinguish Board-corrected scores from raw evaluator totals.

Human-gate invariants (unchanged):
    scanned_scripts.status → MARKS_SUBMITTED only via evaluator submit endpoint (Gate 1).
    scanned_scripts.status → BOARD_FINALISED only via board finalise endpoint (Gate 2).
    exam_score_ledger is NEVER written by any Celery task.
    board_adjusted_marks is NEVER set by any Celery task — only by Board correction endpoint.

New ScriptStatus values (stored as VARCHAR; no PostgreSQL ENUM type):
    QUALITY_CHECKING — detect_scan_quality task running
    QUALITY_FAILED   — scan rejected; admin must re-upload or override
    OCR_PROCESSING   — ocr_scanned_script task running
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0025ten"
down_revision = "0024ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New table: scanned_script_batches (exam bundle workflow)
    # ------------------------------------------------------------------
    op.create_table(
        "scanned_script_batches",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exam_paper_id",   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label",           sa.String(),                   nullable=True),
        sa.Column("file_count",      sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(),                  nullable=False, server_default="0"),
        sa.Column("status",          sa.String(),                   nullable=False, server_default="PENDING"),
        sa.Column("created_at",      sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_ssb_exam_paper",  "scanned_script_batches", ["exam_paper_id"])
    op.create_index("ix_ssb_uploaded_by", "scanned_script_batches", ["uploaded_by"])
    op.create_index("ix_ssb_status",      "scanned_script_batches", ["status"])
    op.create_index("ix_ssb_created",     "scanned_script_batches", ["created_at"])

    # ------------------------------------------------------------------
    # 2. exam_papers — M08→M09 integration: double evaluation config
    # ------------------------------------------------------------------
    op.add_column(
        "exam_papers",
        sa.Column(
            "double_evaluation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "exam_papers",
        sa.Column(
            "discrepancy_threshold_pct",
            sa.Numeric(4, 1),
            nullable=True,
            server_default="20.0",
        ),
    )
    op.create_index(
        "ix_exam_papers_double_eval",
        "exam_papers",
        ["double_evaluation_enabled"],
    )

    # ------------------------------------------------------------------
    # 3. scanned_scripts — quality flags, batch link, viewer columns
    # ------------------------------------------------------------------
    op.add_column(
        "scanned_scripts",
        sa.Column("ocr_quality_score",  sa.Numeric(4, 2),  nullable=True),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column("scan_quality_flags", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scanned_script_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column("duplicate_of",     postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "scanned_scripts",
        sa.Column("page_image_keys",  postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_scanned_scripts_batch",     "scanned_scripts", ["batch_id"])
    op.create_index("ix_scanned_scripts_duplicate", "scanned_scripts", ["duplicate_of"])

    # ------------------------------------------------------------------
    # 4. script_evaluations — AI enrichment + Board correction
    # ------------------------------------------------------------------
    op.add_column(
        "script_evaluations",
        sa.Column("keyword_hits",          postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "script_evaluations",
        sa.Column("rubric_mapping",        postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "script_evaluations",
        sa.Column("ai_confidence",         sa.Numeric(4, 3),   nullable=True),
    )
    op.add_column(
        "script_evaluations",
        sa.Column("page_range",            postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "script_evaluations",
        sa.Column("board_adjusted_marks",  sa.Numeric(5, 1),   nullable=True),
    )
    op.add_column(
        "script_evaluations",
        sa.Column("board_adjustment_note", sa.Text(),          nullable=True),
    )

    # ------------------------------------------------------------------
    # 5. exam_score_ledger — M09→M10 integration flag
    # ------------------------------------------------------------------
    op.add_column(
        "exam_score_ledger",
        sa.Column(
            "has_board_adjustment",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    # Reverse order
    op.drop_column("exam_score_ledger",   "has_board_adjustment")

    op.drop_column("script_evaluations",  "board_adjustment_note")
    op.drop_column("script_evaluations",  "board_adjusted_marks")
    op.drop_column("script_evaluations",  "page_range")
    op.drop_column("script_evaluations",  "ai_confidence")
    op.drop_column("script_evaluations",  "rubric_mapping")
    op.drop_column("script_evaluations",  "keyword_hits")

    op.drop_index("ix_scanned_scripts_duplicate", table_name="scanned_scripts")
    op.drop_index("ix_scanned_scripts_batch",     table_name="scanned_scripts")
    op.drop_column("scanned_scripts",  "page_image_keys")
    op.drop_column("scanned_scripts",  "duplicate_of")
    op.drop_column("scanned_scripts",  "batch_id")
    op.drop_column("scanned_scripts",  "scan_quality_flags")
    op.drop_column("scanned_scripts",  "ocr_quality_score")

    op.drop_index("ix_exam_papers_double_eval",   table_name="exam_papers")
    op.drop_column("exam_papers", "discrepancy_threshold_pct")
    op.drop_column("exam_papers", "double_evaluation_enabled")

    op.drop_table("scanned_script_batches")
