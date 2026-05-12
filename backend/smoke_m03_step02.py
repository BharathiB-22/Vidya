"""STEP-02 smoke tests — M03 DB models + migration 0007."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",    "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",   "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.modules.m03_course_kit.models import (
    CourseKitStatus, ComplexityLevel, QuizletType, AssignmentType, BloomLevel,
    CourseKit, KitSlide, KitQuizlet, KitAssignment,
)
from app.database import Base

# 1. All 5 enums importable and correct values
assert set(CourseKitStatus)  == {"DRAFT", "AI_GENERATING", "PUBLISHED", "ARCHIVED"}
assert set(ComplexityLevel)  == {"UG", "PG"}
assert set(QuizletType)      == {"MCQ", "SHORT_ANSWER"}
assert set(AssignmentType)   == {"CLASSWORK", "HOMEWORK", "CASE_STUDY"}
assert set(BloomLevel)       == {"REMEMBER", "UNDERSTAND", "APPLY", "ANALYSE", "EVALUATE", "CREATE"}

# 2. All 4 ORM models registered in Base.metadata
table_names = set(Base.metadata.tables.keys())
for t in ("course_kits", "kit_slides", "kit_quizlets", "kit_assignments"):
    assert t in table_names, f"Table {t!r} missing from Base.metadata"

# 3. CourseKit: key columns present
ck_cols = {c.name for c in CourseKit.__table__.columns}
for col in ("id", "syllabus_id", "unit_number", "version", "parent_version_id",
            "status", "complexity_level", "tone", "custom_instructions",
            "teaching_plan", "lesson_plans", "resources",
            "ai_model", "prompt_hash", "created_by_user_id",
            "published_by_user_id", "published_at", "created_at", "updated_at"):
    assert col in ck_cols, f"CourseKit missing column {col!r}"

# 4. KitSlide: speaker_notes present (faculty-only field)
slide_cols = {c.name for c in KitSlide.__table__.columns}
for col in ("id", "kit_id", "slide_number", "title", "content",
            "speaker_notes", "bloom_level", "co_reference"):
    assert col in slide_cols, f"KitSlide missing column {col!r}"

# 5. KitQuizlet: answer_key present and NOT nullable
quizlet_cols = {c.name: c for c in KitQuizlet.__table__.columns}
for col in ("id", "kit_id", "question_number", "question_text",
            "question_type", "options", "answer_key",
            "answer_explanation", "bloom_level", "co_reference"):
    assert col in quizlet_cols, f"KitQuizlet missing column {col!r}"
assert not quizlet_cols["answer_key"].nullable, "answer_key must be NOT NULL"

# 6. KitAssignment: model_answer nullable (it's set after creation), rubric present
assign_cols = {c.name: c for c in KitAssignment.__table__.columns}
for col in ("id", "kit_id", "assignment_number", "title", "assignment_type",
            "question_text", "complexity_level", "current_events_toggle",
            "model_answer", "rubric", "bloom_level", "co_reference"):
    assert col in assign_cols, f"KitAssignment missing column {col!r}"
assert assign_cols["model_answer"].nullable, "model_answer should be nullable"

# 7. Unique constraints: UC(kit_id, slide_number), UC(kit_id, question_number), UC(kit_id, assignment_number)
def _has_uc(table, *cols):
    col_set = set(cols)
    for c in table.constraints:
        from sqlalchemy import UniqueConstraint as UC
        if isinstance(c, UC):
            if {col.name for col in c.columns} == col_set:
                return True
    return False

assert _has_uc(KitSlide.__table__,      "kit_id", "slide_number"),      "KitSlide UC missing"
assert _has_uc(KitQuizlet.__table__,    "kit_id", "question_number"),   "KitQuizlet UC missing"
assert _has_uc(KitAssignment.__table__, "kit_id", "assignment_number"), "KitAssignment UC missing"

# 8. Relationships wired correctly
assert hasattr(CourseKit,    "slides")
assert hasattr(CourseKit,    "quizlets")
assert hasattr(CourseKit,    "assignments")
assert hasattr(CourseKit,    "parent_version")
assert hasattr(KitSlide,     "kit")
assert hasattr(KitQuizlet,   "kit")
assert hasattr(KitAssignment,"kit")

# 9. Migration file exists with correct revision chain
import pathlib
migration = pathlib.Path(__file__).parent / "alembic/tenant_versions/0007_tenant_create_m03_course_kit.py"
assert migration.exists(), "Migration file 0007 missing"
src = migration.read_text()
assert 'revision      = "0007ten"'  in src, "revision ID wrong"
assert 'down_revision = "0006ten"'  in src, "down_revision wrong"
assert '"course_kits"'              in src, "course_kits table missing from migration"
assert '"kit_slides"'               in src, "kit_slides table missing from migration"
assert '"kit_quizlets"'             in src, "kit_quizlets table missing from migration"
assert '"kit_assignments"'          in src, "kit_assignments table missing from migration"

# 10. All enums are native_enum=False (str storage, not PG enum type)
for col in CourseKit.__table__.columns:
    if hasattr(col.type, "native_enum"):
        assert col.type.native_enum is False, f"Column {col.name} has native_enum=True"

print("STEP-02: all 10 assertions passed.")
