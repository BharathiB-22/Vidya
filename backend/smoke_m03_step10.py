"""
Smoke tests for STEP-10: M03 export workflow (PPTX + PDF).

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step10.py
"""
import os
import sys
import inspect

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("AI_PROVIDER", "groq")

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


# ---------------------------------------------------------------------------
# 1. StorageRepository _KEY_PATTERN accepts course_kit_export
# ---------------------------------------------------------------------------
print("\n--- StorageRepository key pattern ---")
try:
    from app.core.storage.repository import StorageRepository
    check("StorageRepository imports cleanly", True)
except Exception as exc:
    check(f"StorageRepository import failed: {exc}", False)
    sys.exit(1)

import re
pattern = StorageRepository._KEY_PATTERN

VALID_KEY = (
    "vidya-assets/testcorp/course_kit_export"
    "/00000000-0000-0000-0000-000000000001"
    "/00000000-0000-0000-0000-000000000002-kit_cs101_u1_v1.pdf"
)
INVALID_KEY_OLD_TYPE = (
    "vidya-assets/testcorp/unknown_type"
    "/00000000-0000-0000-0000-000000000001"
    "/00000000-0000-0000-0000-000000000002-file.pdf"
)
VALID_SYLLABUS_KEY = (
    "vidya-assets/testcorp/syllabus_export"
    "/00000000-0000-0000-0000-000000000003"
    "/00000000-0000-0000-0000-000000000004-syllabus_v1.pdf"
)

check("course_kit_export key passes validation",
      bool(pattern.match(VALID_KEY)))
check("syllabus_export key still passes (regression)",
      bool(pattern.match(VALID_SYLLABUS_KEY)))
check("unknown entity type still rejected",
      not bool(pattern.match(INVALID_KEY_OLD_TYPE)))
check("'course_kit_export' in pattern source",
      "course_kit_export" in pattern.pattern)

# ---------------------------------------------------------------------------
# 2. Celery export task imports and structure
# ---------------------------------------------------------------------------
print("\n--- Celery export task ---")
try:
    from app.workers.heavy.course_kit_export import export_course_kit, _run_export
    check("course_kit_export module imports cleanly", True)
except Exception as exc:
    check(f"course_kit_export import failed: {exc}", False)
    sys.exit(1)

check("export_course_kit has .delay method",
      hasattr(export_course_kit, "delay"))
check("export_course_kit task name correct",
      export_course_kit.name == "app.workers.heavy.export_course_kit")
check("export_course_kit has max_retries=3",
      export_course_kit.max_retries == 3)
check("_run_export is a coroutine function",
      inspect.iscoroutinefunction(_run_export))

# ---------------------------------------------------------------------------
# 3. _run_export signature
# ---------------------------------------------------------------------------
print("\n--- _run_export signature ---")
sig    = inspect.signature(_run_export)
params = set(sig.parameters.keys())
check("param: kit_id",              "kit_id"               in params)
check("param: tenant_id",           "tenant_id"            in params)
check("param: schema_name",         "schema_name"          in params)
check("param: export_format",       "export_format"        in params)
check("param: requested_by_user_id","requested_by_user_id" in params)
check("param: requested_by_role",   "requested_by_role"    in params)

# ---------------------------------------------------------------------------
# 4. export_course_kit has requested_by_role param with default
# ---------------------------------------------------------------------------
print("\n--- export_course_kit task signature ---")
task_sig    = inspect.signature(export_course_kit.run)
task_params = task_sig.parameters
check("task has requested_by_role param",
      "requested_by_role" in task_params)
check("requested_by_role defaults to FACULTY",
      task_params.get("requested_by_role") is not None
      and task_params["requested_by_role"].default == "FACULTY")

# ---------------------------------------------------------------------------
# 5. Celery include list
# ---------------------------------------------------------------------------
print("\n--- Celery include list ---")
from app.workers.celery_app import celery_app
check("course_kit_export in celery_app include",
      "app.workers.heavy.course_kit_export" in celery_app.conf.include)
check("course_kit_generation still in include (no regression)",
      "app.workers.heavy.course_kit_generation" in celery_app.conf.include)
check("syllabus_export still in include (no regression)",
      "app.workers.heavy.syllabus_export" in celery_app.conf.include)

# ---------------------------------------------------------------------------
# 6. PPTX generator is callable (import-only test — no real presentation built)
# ---------------------------------------------------------------------------
print("\n--- Generator callability ---")
try:
    from app.workers.heavy.course_kit_export import _generate_pptx, _generate_pdf
    check("_generate_pptx importable", True)
    check("_generate_pdf importable", True)
except Exception as exc:
    check(f"generator import failed: {exc}", False)
    sys.exit(1)

check("_generate_pptx is callable", callable(_generate_pptx))
check("_generate_pdf is callable", callable(_generate_pdf))

# ---------------------------------------------------------------------------
# 7. Dry-run: PDF generation with in-memory mock objects
# ---------------------------------------------------------------------------
print("\n--- PDF dry-run (in-memory mock) ---")
try:
    import io
    from types import SimpleNamespace

    def _mock_kit():
        kit = SimpleNamespace(
            unit_number=1, version=1,
            status=SimpleNamespace(value="PUBLISHED"),
            complexity_level=SimpleNamespace(value="UG"),
            published_at=None, ai_model="groq/llama-3",
            teaching_plan=[],
            resources=[],
            slides=[
                SimpleNamespace(
                    slide_number=1, title="Introduction",
                    content={"bullets": ["Bullet one", "Bullet two"], "key_concepts": ["OOP"]},
                    speaker_notes="Faculty note here",
                    bloom_level=SimpleNamespace(value="UNDERSTAND"),
                    co_reference="CO1",
                )
            ],
            quizlets=[
                SimpleNamespace(
                    question_number=1,
                    question_type=SimpleNamespace(value="MCQ"),
                    question_text="What is encapsulation?",
                    options=[{"label": "A", "text": "Hiding data"}],
                    answer_key={"answer": "A"},
                    answer_explanation="Encapsulation hides internal state.",
                    bloom_level=None,
                )
            ],
            assignments=[
                SimpleNamespace(
                    assignment_number=1, title="Case Study",
                    assignment_type=SimpleNamespace(value="CASE_STUDY"),
                    question_text="Analyse the following design pattern...",
                    complexity_level=SimpleNamespace(value="UG"),
                    model_answer="Model answer text here.",
                    rubric=[
                        {"criterion": "Accuracy", "description": "Correct analysis", "max_marks": 5}
                    ],
                    bloom_level=None,
                )
            ],
        )
        return kit

    def _mock_course():
        return SimpleNamespace(code="CS101", title="Introduction to Programming")

    buf = io.BytesIO()
    _generate_pdf(buf, _mock_kit(), _mock_course(), is_dean=False)
    pdf_bytes = buf.getvalue()
    check("PDF generated without error",        len(pdf_bytes) > 0)
    check("PDF starts with %PDF magic bytes",   pdf_bytes[:4] == b"%PDF")

    buf_dean = io.BytesIO()
    _generate_pdf(buf_dean, _mock_kit(), _mock_course(), is_dean=True)
    dean_pdf = buf_dean.getvalue()
    check("DEAN PDF generated without error",   len(dean_pdf) > 0)

    # DEAN PDF should not contain sensitive strings
    dean_text = dean_pdf.decode("latin-1", errors="ignore")
    check("DEAN PDF does not contain speaker notes",
          "Faculty note here" not in dean_text)
    check("DEAN PDF does not contain model answer",
          "Model answer text here" not in dean_text)

except Exception as exc:
    check(f"PDF dry-run failed: {exc}", False)

# ---------------------------------------------------------------------------
# 8. PPTX dry-run
# ---------------------------------------------------------------------------
print("\n--- PPTX dry-run (in-memory mock) ---")
try:
    buf_pptx = io.BytesIO()
    _generate_pptx(buf_pptx, _mock_kit(), _mock_course(), is_dean=False)
    pptx_bytes = buf_pptx.getvalue()
    check("PPTX generated without error",    len(pptx_bytes) > 0)
    # PPTX is a zip file starting with PK
    check("PPTX starts with PK zip header", pptx_bytes[:2] == b"PK")
except Exception as exc:
    check(f"PPTX dry-run failed: {exc}", False)

# ---------------------------------------------------------------------------
# 9. Service methods exist
# ---------------------------------------------------------------------------
print("\n--- Service export methods ---")
from app.modules.m03_course_kit.service import CourseKitService
check("dispatch_kit_export exists",
      hasattr(CourseKitService, "dispatch_kit_export"))
check("list_exports exists",
      hasattr(CourseKitService, "list_exports"))
check("get_export_download exists",
      hasattr(CourseKitService, "get_export_download"))
check("dispatch_kit_export is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.dispatch_kit_export))
check("list_exports is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.list_exports))

sig_dispatch = inspect.signature(CourseKitService.dispatch_kit_export)
dispatch_params = set(sig_dispatch.parameters.keys())
check("dispatch: kit_id param",           "kit_id"            in dispatch_params)
check("dispatch: export_format param",    "export_format"     in dispatch_params)
check("dispatch: requested_by_role param","requested_by_role" in dispatch_params)
check("dispatch: tenant_id param",        "tenant_id"         in dispatch_params)
check("dispatch: schema_name param",      "schema_name"       in dispatch_params)

# ---------------------------------------------------------------------------
# 10. Router export routes (29 total = 26 original + 3 export)
# ---------------------------------------------------------------------------
print("\n--- Router export routes ---")
from app.modules.m03_course_kit.router import router
from fastapi import APIRouter

check("router has exactly 29 routes", len(router.routes) == 29)

all_paths = [getattr(r, "path", "") for r in router.routes]
check("POST /{kit_id}/export registered",
      "/{kit_id}/export" in all_paths)
check("GET  /{kit_id}/exports registered",
      "/{kit_id}/exports" in all_paths)
check("GET  /{kit_id}/exports/{asset_id}/download registered",
      "/{kit_id}/exports/{asset_id}/download" in all_paths)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-10 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-10 smoke tests green.")
