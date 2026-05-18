"""tenant: create m09 paper administration tables

Revision ID: 0012ten
Revises: 0011ten
Create Date: 2026-05-18

Tables created (tenant schema):
  scanned_scripts     — one record per uploaded answer script
  script_evaluations  — AI + human marks per question per script per evaluation round
  exam_score_ledger   — append-only Board-finalised marks

Human-gate invariants:
  scanned_scripts.status → MARKS_SUBMITTED only via evaluator submit endpoint (Gate 1).
  scanned_scripts.status → BOARD_FINALISED only via board finalise endpoint (Gate 2).
  No Celery task ever sets status beyond SCORED.
  exam_score_ledger is NEVER written by any Celery task.
  script_evaluations.evaluator_marks is NEVER set by any Celery task.
  scanned_scripts.student_user_id is NEVER returned via API until BOARD_FINALISED.

OCR fields (ocr_status, ocr_text) are schema placeholders — no OCR logic this sprint.
Locking fields (locked_by, locked_at) are schema placeholders — no locking logic this sprint.
evaluation_round supports future SECONDARY/MODERATION workflows without schema redesign.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision      = "0012ten"
down_revision = "0011ten"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. scanned_scripts
    # ------------------------------------------------------------------
    op.create_table(
        "scanned_scripts",
        sa.Column("id",                    postgresql.UUID(as_uuid=True), primary_key=True),
        # FK to exam_papers.id in same tenant schema
        sa.Column("exam_paper_id",         postgresql.UUID(as_uuid=True), nullable=False),
        # Opaque token — the only identifier exposed to evaluators during evaluation
        sa.Column("masked_id",             sa.String(),                   nullable=False, unique=True),
        # Student identity — NEVER returned via API until status == BOARD_FINALISED
        sa.Column("student_user_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_roll_ref",      sa.String(),                   nullable=True),
        # S3 object key for scanned PDF
        sa.Column("upload_url",            sa.String(),                   nullable=True),
        sa.Column("page_count",            sa.Integer(),                  nullable=True),
        # Workflow status
        sa.Column("status",                sa.String(),                   nullable=False, server_default="PENDING"),
        # Celery job FK (public.task_jobs)
        sa.Column("eval_job_id",           postgresql.UUID(as_uuid=True), nullable=True),
        # MCQ auto-score sum written by Celery task
        sa.Column("objective_auto_score",  sa.Numeric(6, 2),              nullable=True),
        # Evaluator assignments
        sa.Column("evaluator_id",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("second_evaluator_id",   postgresql.UUID(as_uuid=True), nullable=True),
        # Gate 1: evaluator submits — written ONLY by submit_marks endpoint
        sa.Column("submitted_by",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at",          sa.DateTime(timezone=True),    nullable=True),
        # Gate 2: Board finalises — written ONLY by board_finalise endpoint
        sa.Column("finalised_by",          postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("finalised_at",          sa.DateTime(timezone=True),    nullable=True),
        # OCR placeholders — no implementation this sprint
        sa.Column("ocr_status",            sa.String(),                   nullable=True),
        sa.Column("ocr_text",              sa.Text(),                     nullable=True),
        # Locking placeholders — no locking logic this sprint
        sa.Column("locked_by",             postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locked_at",             sa.DateTime(timezone=True),    nullable=True),
        sa.Column("created_at",            sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",            sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_index("ix_scanned_scripts_exam_paper",  "scanned_scripts", ["exam_paper_id"])
    op.create_index("ix_scanned_scripts_student",     "scanned_scripts", ["student_user_id"])
    op.create_index("ix_scanned_scripts_status",      "scanned_scripts", ["status"])
    op.create_index("ix_scanned_scripts_evaluator",   "scanned_scripts", ["evaluator_id"])
    op.create_unique_constraint(
        "uq_scanned_scripts_masked_id", "scanned_scripts", ["masked_id"]
    )
    op.create_index("ix_scanned_scripts_masked_id",   "scanned_scripts", ["masked_id"])
    op.create_index("ix_scanned_scripts_created",     "scanned_scripts", ["created_at"])

    # ------------------------------------------------------------------
    # 2. script_evaluations
    # ------------------------------------------------------------------
    op.create_table(
        "script_evaluations",
        sa.Column("id",                    postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("script_id",             postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("scanned_scripts.id", ondelete="CASCADE"), nullable=False),
        # FK to exam_questions.id in same tenant schema (no ORM FK; same schema)
        sa.Column("question_id",           postgresql.UUID(as_uuid=True), nullable=False),
        # Denormalized from exam_questions for display
        sa.Column("question_type",         sa.String(),                   nullable=False),
        sa.Column("max_marks",             sa.Numeric(5, 1),              nullable=False),
        # Evaluation round: PRIMARY (this sprint) / SECONDARY / MODERATION (future)
        sa.Column("evaluation_round",      sa.String(),                   nullable=False, server_default="PRIMARY"),
        # AI suggestion — written ONLY by Celery score task
        sa.Column("ai_suggested_marks",    sa.Numeric(5, 1),              nullable=True),
        sa.Column("ai_justification",      sa.Text(),                     nullable=True),
        sa.Column("ai_model",              sa.String(),                   nullable=True),
        sa.Column("prompt_hash",           sa.String(),                   nullable=True),
        # Human marks — written ONLY by evaluator endpoints, NEVER by Celery
        sa.Column("evaluator_marks",       sa.Numeric(5, 1),              nullable=True),
        sa.Column("evaluator_note",        sa.Text(),                     nullable=True),
        # Final marks — set by board_finalise (copied from evaluator_marks)
        sa.Column("final_marks",           sa.Numeric(5, 1),              nullable=True),
        sa.Column("created_at",            sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",            sa.DateTime(timezone=True),    nullable=True),
    )
    op.create_unique_constraint(
        "uq_script_eval_script_question_round",
        "script_evaluations",
        ["script_id", "question_id", "evaluation_round"],
    )
    op.create_index("ix_script_evaluations_script",   "script_evaluations", ["script_id"])
    op.create_index("ix_script_evaluations_question", "script_evaluations", ["question_id"])
    op.create_index("ix_script_evaluations_round",    "script_evaluations", ["evaluation_round"])

    # ------------------------------------------------------------------
    # 3. exam_score_ledger  — append-only; no UPDATE or DELETE ever
    # ------------------------------------------------------------------
    op.create_table(
        "exam_score_ledger",
        sa.Column("id",                    postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("script_id",             postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("scanned_scripts.id", ondelete="RESTRICT"),
                  nullable=False, unique=True),
        # Denormalized for reporting
        sa.Column("exam_paper_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_user_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("student_roll_ref",      sa.String(),                   nullable=True),
        # Marks at finalisation time
        sa.Column("total_marks",           sa.Numeric(6, 2),              nullable=False),
        sa.Column("max_marks",             sa.Numeric(6, 2),              nullable=False),
        # Board member who finalised
        sa.Column("finalised_by",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finalisation_note",     sa.Text(),                     nullable=True),
        sa.Column("finalised_at",          sa.DateTime(timezone=True),    nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_exam_score_ledger_script", "exam_score_ledger", ["script_id"]
    )
    op.create_index("ix_exam_score_ledger_script",       "exam_score_ledger", ["script_id"])
    op.create_index("ix_exam_score_ledger_exam_paper",   "exam_score_ledger", ["exam_paper_id"])
    op.create_index("ix_exam_score_ledger_student",      "exam_score_ledger", ["student_user_id"])
    op.create_index("ix_exam_score_ledger_finalised_by", "exam_score_ledger", ["finalised_by"])
    op.create_index("ix_exam_score_ledger_finalised_at", "exam_score_ledger", ["finalised_at"])


def downgrade() -> None:
    op.drop_table("exam_score_ledger")
    op.drop_table("script_evaluations")
    op.drop_table("scanned_scripts")
