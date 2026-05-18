"""STEP-01 smoke test — M08 models and migration file."""
import importlib.util, pathlib

# -- Model imports --
from app.modules.m08_exam_setter.models import (
    ExamPaper, ExamQuestion, BloomsComplianceReport,
    ExamType, ExamPaperStatus, QuestionType, BloomLevel,
)

# Table names
assert ExamPaper.__tablename__ == "exam_papers",                  "ExamPaper table name wrong"
assert ExamQuestion.__tablename__ == "exam_questions",            "ExamQuestion table name wrong"
assert BloomsComplianceReport.__tablename__ == "blooms_compliance_reports", "BloomsReport table name wrong"

# ExamType enum values
assert ExamType.MID_SEM  == "MID_SEM"
assert ExamType.END_SEM  == "END_SEM"
assert ExamType.QUIZ     == "QUIZ"
assert ExamType.INTERNAL == "INTERNAL"
assert ExamType.CUSTOM   == "CUSTOM"

# ExamPaperStatus enum values — all 8 states
assert ExamPaperStatus.DRAFT          == "DRAFT"
assert ExamPaperStatus.GENERATING     == "GENERATING"
assert ExamPaperStatus.GENERATED      == "GENERATED"
assert ExamPaperStatus.SUBMITTED      == "SUBMITTED"
assert ExamPaperStatus.BOARD_APPROVED == "BOARD_APPROVED"
assert ExamPaperStatus.BOARD_RETURNED == "BOARD_RETURNED"
assert ExamPaperStatus.SEALED         == "SEALED"
assert ExamPaperStatus.RELEASED       == "RELEASED"

# QuestionType enum values
assert QuestionType.MCQ             == "MCQ"
assert QuestionType.SHORT_ANSWER    == "SHORT_ANSWER"
assert QuestionType.LONG_ANSWER     == "LONG_ANSWER"
assert QuestionType.PROBLEM_SOLVING == "PROBLEM_SOLVING"

# BloomLevel enum values — all 6 levels
assert BloomLevel.REMEMBER   == "REMEMBER"
assert BloomLevel.UNDERSTAND == "UNDERSTAND"
assert BloomLevel.APPLY      == "APPLY"
assert BloomLevel.ANALYSE    == "ANALYSE"
assert BloomLevel.EVALUATE   == "EVALUATE"
assert BloomLevel.CREATE     == "CREATE"

# Human-gate columns present on ExamPaper
assert hasattr(ExamPaper, "submitted_at"),       "submitted_at missing"
assert hasattr(ExamPaper, "approved_by"),        "approved_by missing (Gate 2)"
assert hasattr(ExamPaper, "approved_at"),        "approved_at missing (Gate 2)"
assert hasattr(ExamPaper, "board_comment"),      "board_comment missing"
assert hasattr(ExamPaper, "sealed_at"),          "sealed_at missing (Gate 3)"
assert hasattr(ExamPaper, "release_at"),         "release_at missing"
assert hasattr(ExamPaper, "encrypted_blob_key"), "encrypted_blob_key missing"
assert hasattr(ExamPaper, "encryption_key_ref"), "encryption_key_ref missing (NOT the key)"
assert hasattr(ExamPaper, "released_at"),        "released_at missing"

# ExamQuestion columns
assert hasattr(ExamQuestion, "model_answer"),   "model_answer missing"
assert hasattr(ExamQuestion, "marking_scheme"), "marking_scheme missing"
assert hasattr(ExamQuestion, "set_membership"), "set_membership missing"
assert hasattr(ExamQuestion, "is_edited"),      "is_edited missing"
assert hasattr(ExamQuestion, "correct_option"), "correct_option missing (MCQ)"

# BloomsComplianceReport
assert hasattr(BloomsComplianceReport, "compliance_ok"), "compliance_ok missing"
assert hasattr(BloomsComplianceReport, "violations"),    "violations missing"

# -- Migration file --
mig_path = pathlib.Path("alembic/tenant_versions/0011_tenant_create_m08_exam.py")
spec = importlib.util.spec_from_file_location("mig0011", mig_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

assert m.revision      == "0011ten",   f"expected 0011ten, got {m.revision}"
assert m.down_revision == "0010ten",   f"expected 0010ten, got {m.down_revision}"
print(f"revision:      {m.revision}")
print(f"down_revision: {m.down_revision}")
print("Migration chain OK")
print("All STEP-01 assertions passed.")
