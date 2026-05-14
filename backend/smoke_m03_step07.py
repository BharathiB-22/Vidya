"""
Smoke tests for STEP-07: M03 service layer + router.

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step07.py
"""
import os
import sys
import inspect
from datetime import datetime, timezone
from uuid import uuid4

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
# 1. Service module imports
# ---------------------------------------------------------------------------
print("\n--- Service module imports ---")
try:
    from app.modules.m03_course_kit.service import (
        CourseKitService,
        KitServiceError,
        _build_compliance,
    )
    check("service module imports cleanly", True)
except Exception as exc:
    check(f"service import failed: {exc}", False)
    sys.exit(1)

check("KitServiceError is an Exception subclass", issubclass(KitServiceError, Exception))
check("_build_compliance is callable", callable(_build_compliance))

# ---------------------------------------------------------------------------
# 2. KitServiceError attributes
# ---------------------------------------------------------------------------
print("\n--- KitServiceError attributes ---")
err = KitServiceError("NOT_FOUND", "Kit missing.", 404)
check("code attribute correct",        err.code        == "NOT_FOUND")
check("message attribute correct",     err.message     == "Kit missing.")
check("status_code attribute correct", err.status_code == 404)

err_default = KitServiceError("X", "msg")
check("default status_code is 400", err_default.status_code == 400)

# ---------------------------------------------------------------------------
# 3. All service methods exist on CourseKitService
# ---------------------------------------------------------------------------
print("\n--- Service method existence ---")
SERVICE_METHODS = [
    "dispatch_kit_generation",
    "create_kit", "get_kit", "get_kit_detail", "list_kits",
    "update_kit", "delete_kit", "list_versions",
    "publish_kit", "archive_kit", "fork_kit",
    "run_compliance_check", "get_job_status",
    "list_slides", "add_slide", "update_slide", "delete_slide", "reorder_slides",
    "list_quizlets", "add_quizlet", "update_quizlet", "delete_quizlet",
    "list_assignments", "add_assignment", "update_assignment", "delete_assignment",
]
missing = [m for m in SERVICE_METHODS if not hasattr(CourseKitService, m)]
check(f"all 26 methods present on CourseKitService (missing: {missing})", len(missing) == 0)

# ---------------------------------------------------------------------------
# 4. Key methods are coroutine functions
# ---------------------------------------------------------------------------
print("\n--- Service coroutine check ---")
check("create_kit is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.create_kit))
check("publish_kit is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.publish_kit))
check("fork_kit is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.fork_kit))
check("run_compliance_check is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.run_compliance_check))
check("dispatch_kit_generation is a coroutine",
      inspect.iscoroutinefunction(CourseKitService.dispatch_kit_generation))

# ---------------------------------------------------------------------------
# 5. dispatch_kit_generation signature
# ---------------------------------------------------------------------------
print("\n--- dispatch_kit_generation signature ---")
sig = inspect.signature(CourseKitService.dispatch_kit_generation)
params = set(sig.parameters.keys())
check("param: kit_id",     "kit_id"      in params)
check("param: tenant_id",  "tenant_id"   in params)
check("param: schema_name","schema_name" in params)
check("param: db",         "db"          in params)

# ---------------------------------------------------------------------------
# 6. _build_compliance logic (pure function — no DB needed)
# ---------------------------------------------------------------------------
print("\n--- _build_compliance logic ---")

# Below minimum on everything: not passed, 3 violations
r_empty = _build_compliance(
    slide_count=0, quizlet_count=0, teaching_plan=[],
    min_slides=8, min_quizlets=2,
)
check("empty kit: passed=False",        r_empty.passed is False)
check("empty kit: 3 violations",        len(r_empty.violations) == 3)
check("SLIDE_MIN_NOT_MET present",
      any(v.code == "SLIDE_MIN_NOT_MET"  for v in r_empty.violations))
check("QUIZLET_MIN_NOT_MET present",
      any(v.code == "QUIZLET_MIN_NOT_MET" for v in r_empty.violations))
check("NO_TEACHING_PLAN present",
      any(v.code == "NO_TEACHING_PLAN"   for v in r_empty.violations))

# At or above minimum with teaching plan: fully passed
r_pass = _build_compliance(
    slide_count=8, quizlet_count=2,
    teaching_plan=[{"week": 1, "topic": "Intro"}],
    min_slides=8, min_quizlets=2,
)
check("full kit: passed=True",     r_pass.passed is True)
check("full kit: 0 violations",    len(r_pass.violations) == 0)

# Slides and quizlets OK, but no teaching plan: WARNING only, still passed
r_warn = _build_compliance(
    slide_count=10, quizlet_count=3, teaching_plan=[],
    min_slides=8, min_quizlets=2,
)
check("no-plan kit: passed=True (WARNING is advisory)",  r_warn.passed is True)
check("no-plan kit: exactly 1 violation",                len(r_warn.violations) == 1)
check("no-plan kit: violation is WARNING severity",
      r_warn.violations[0].severity == "WARNING")

# Only slide count below minimum: ERROR blocks publish
r_slide_fail = _build_compliance(
    slide_count=3, quizlet_count=2,
    teaching_plan=[{"week": 1}],
    min_slides=8, min_quizlets=2,
)
check("slide undercount: passed=False", r_slide_fail.passed is False)

# ---------------------------------------------------------------------------
# 7. Router imports
# ---------------------------------------------------------------------------
print("\n--- Router module ---")
try:
    from app.modules.m03_course_kit.router import (
        router,
        _gate_slide,
        _gate_quizlet,
        _gate_assignment,
        _gate_detail,
        _err,
        _WRITE,
        _READ,
    )
    from fastapi import APIRouter
    check("router module imports cleanly", True)
except Exception as exc:
    check(f"router import failed: {exc}", False)
    sys.exit(1)

check("router is an APIRouter instance", isinstance(router, APIRouter))
check("router has 'course-kits' tag",    "course-kits" in router.tags)
check("router has exactly 26 routes",    len(router.routes) == 26)

# ---------------------------------------------------------------------------
# 8. RBAC role sets
# ---------------------------------------------------------------------------
print("\n--- RBAC role sets ---")
from app.core.auth.models import TenantRole

check("_WRITE contains ADMIN",   TenantRole.ADMIN   in _WRITE)
check("_WRITE contains FACULTY", TenantRole.FACULTY in _WRITE)
check("_WRITE excludes DEAN",    TenantRole.DEAN not in _WRITE)
check("_READ contains DEAN",     TenantRole.DEAN    in _READ)
check("_READ contains FACULTY",  TenantRole.FACULTY in _READ)
check("_READ contains ADMIN",    TenantRole.ADMIN   in _READ)

# ---------------------------------------------------------------------------
# 9. DEAN sensitive-field gating helpers
# ---------------------------------------------------------------------------
print("\n--- DEAN gating helpers ---")
from app.modules.m03_course_kit.schemas import (
    AssignmentType,
    BloomLevel,
    ComplexityLevel,
    KitAssignmentResponse,
    KitQuizletResponse,
    KitSlideResponse,
    QuizletType,
)

_now = datetime.now(timezone.utc)
_kid = uuid4()

slide = KitSlideResponse(
    id=uuid4(), kit_id=_kid, slide_number=1, title="Slide 1",
    content={"bullets": []}, speaker_notes="Faculty-only notes",
    bloom_level=None, co_reference=None, created_at=_now, updated_at=None,
)
quizlet = KitQuizletResponse(
    id=uuid4(), kit_id=_kid, question_number=1,
    question_text="What is encapsulation?", question_type=QuizletType.MCQ,
    options=[], answer_key={"answer": "A"}, answer_explanation=None,
    bloom_level=None, co_reference=None, created_at=_now, updated_at=None,
)
assignment = KitAssignmentResponse(
    id=uuid4(), kit_id=_kid, assignment_number=1, title="Case Study",
    assignment_type=AssignmentType.CASE_STUDY, question_text="Analyse the following...",
    complexity_level=ComplexityLevel.UG, current_events_toggle=False,
    model_answer="The model answer is...", rubric=[],
    bloom_level=None, co_reference=None, created_at=_now, updated_at=None,
)

dean_role    = TenantRole.DEAN.value
faculty_role = TenantRole.FACULTY.value

# FACULTY keeps sensitive fields
check("FACULTY: slide speaker_notes preserved",
      _gate_slide(slide, faculty_role).speaker_notes == "Faculty-only notes")
check("FACULTY: quizlet answer_key preserved",
      _gate_quizlet(quizlet, faculty_role).answer_key == {"answer": "A"})
check("FACULTY: assignment model_answer preserved",
      _gate_assignment(assignment, faculty_role).model_answer == "The model answer is...")

# DEAN gets sensitive fields nulled
check("DEAN: slide speaker_notes is None",
      _gate_slide(slide, dean_role).speaker_notes is None)
check("DEAN: quizlet answer_key is None",
      _gate_quizlet(quizlet, dean_role).answer_key is None)
check("DEAN: assignment model_answer is None",
      _gate_assignment(assignment, dean_role).model_answer is None)

# Gating must not mutate the original object (model_copy returns new instance)
check("original slide speaker_notes unchanged after DEAN gate",
      slide.speaker_notes == "Faculty-only notes")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-07 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-07 smoke tests green.")
