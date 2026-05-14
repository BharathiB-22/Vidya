"""
Smoke tests for STEP-08: M03 audit event types + router audit refinement.

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step08.py
"""
import os
import sys

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
# 1. AuditEventType — all 22 M03 events present
# ---------------------------------------------------------------------------
print("\n--- AuditEventType M03 events ---")
try:
    from app.core.audit_log.models import AuditEventType
    check("AuditEventType imports cleanly", True)
except Exception as exc:
    check(f"AuditEventType import failed: {exc}", False)
    sys.exit(1)

M03_EVENTS = [
    # Lifecycle
    "COURSE_KIT_CREATED",
    "COURSE_KIT_UPDATED",
    "COURSE_KIT_DELETED",
    # AI generation (added STEP-06)
    "COURSE_KIT_GENERATION_QUEUED",
    "COURSE_KIT_GENERATION_COMPLETED",
    "COURSE_KIT_GENERATION_FAILED",
    # State transitions
    "COURSE_KIT_PUBLISHED",
    "COURSE_KIT_ARCHIVED",
    "COURSE_KIT_FORKED",
    # Slides
    "COURSE_KIT_SLIDE_ADDED",
    "COURSE_KIT_SLIDE_UPDATED",
    "COURSE_KIT_SLIDE_DELETED",
    "COURSE_KIT_SLIDES_REORDERED",
    # Quizlets
    "COURSE_KIT_QUIZLET_ADDED",
    "COURSE_KIT_QUIZLET_UPDATED",
    "COURSE_KIT_QUIZLET_DELETED",
    # Assignments
    "COURSE_KIT_ASSIGNMENT_ADDED",
    "COURSE_KIT_ASSIGNMENT_UPDATED",
    "COURSE_KIT_ASSIGNMENT_DELETED",
    # Export (STEP-11)
    "COURSE_KIT_EXPORT_REQUESTED",
    "COURSE_KIT_EXPORT_COMPLETED",
    "COURSE_KIT_EXPORT_FAILED",
]

missing_events = [e for e in M03_EVENTS if not hasattr(AuditEventType, e)]
check(
    f"all 22 M03 audit events present (missing: {missing_events})",
    len(missing_events) == 0,
)

# Spot-check enum string values match their names (str enum contract)
check("COURSE_KIT_CREATED value == 'COURSE_KIT_CREATED'",
      AuditEventType.COURSE_KIT_CREATED == "COURSE_KIT_CREATED")
check("COURSE_KIT_PUBLISHED value == 'COURSE_KIT_PUBLISHED'",
      AuditEventType.COURSE_KIT_PUBLISHED == "COURSE_KIT_PUBLISHED")
check("COURSE_KIT_SLIDE_ADDED value == 'COURSE_KIT_SLIDE_ADDED'",
      AuditEventType.COURSE_KIT_SLIDE_ADDED == "COURSE_KIT_SLIDE_ADDED")
check("COURSE_KIT_ASSIGNMENT_DELETED value == 'COURSE_KIT_ASSIGNMENT_DELETED'",
      AuditEventType.COURSE_KIT_ASSIGNMENT_DELETED == "COURSE_KIT_ASSIGNMENT_DELETED")
check("COURSE_KIT_EXPORT_FAILED value == 'COURSE_KIT_EXPORT_FAILED'",
      AuditEventType.COURSE_KIT_EXPORT_FAILED == "COURSE_KIT_EXPORT_FAILED")

# ---------------------------------------------------------------------------
# 2. AuditEventType is still a valid str enum (no broken inheritance)
# ---------------------------------------------------------------------------
print("\n--- AuditEventType integrity ---")
import enum
check("AuditEventType is a str enum",
      issubclass(AuditEventType, str) and issubclass(AuditEventType, enum.Enum))
check("Existing AUTH events unaffected",
      hasattr(AuditEventType, "AUTH_LOGIN_SUCCESS"))
check("Existing M02 events unaffected",
      hasattr(AuditEventType, "SYLLABUS_CREATED"))
check("Existing M01 events unaffected",
      hasattr(AuditEventType, "PROGRAM_CREATED"))

# ---------------------------------------------------------------------------
# 3. Router uses correct events (no placeholder GENERATION_QUEUED misuse)
# ---------------------------------------------------------------------------
print("\n--- Router audit event usage ---")
try:
    import ast, pathlib
    router_src = pathlib.Path(
        "app/modules/m03_course_kit/router.py"
    ).read_text(encoding="utf-8")
    check("router.py read for AST analysis", True)
except Exception as exc:
    check(f"router.py read failed: {exc}", False)
    sys.exit(1)

# Helper: count occurrences of an audit event name in router source
def count_event(src: str, event: str) -> int:
    return src.count(f"AuditEventType.{event}")

# Lifecycle endpoints must use their own events, not placeholders
check("create endpoint uses COURSE_KIT_CREATED",
      count_event(router_src, "COURSE_KIT_CREATED") >= 1)
check("update endpoint uses COURSE_KIT_UPDATED",
      count_event(router_src, "COURSE_KIT_UPDATED") >= 1)
check("delete endpoint uses COURSE_KIT_DELETED",
      count_event(router_src, "COURSE_KIT_DELETED") >= 1)
check("publish endpoint uses COURSE_KIT_PUBLISHED",
      count_event(router_src, "COURSE_KIT_PUBLISHED") >= 1)
check("archive endpoint uses COURSE_KIT_ARCHIVED",
      count_event(router_src, "COURSE_KIT_ARCHIVED") >= 1)
check("fork endpoint uses COURSE_KIT_FORKED",
      count_event(router_src, "COURSE_KIT_FORKED") >= 1)

# Child operations each have their own event
check("add_slide uses COURSE_KIT_SLIDE_ADDED",
      count_event(router_src, "COURSE_KIT_SLIDE_ADDED") >= 1)
check("update_slide uses COURSE_KIT_SLIDE_UPDATED",
      count_event(router_src, "COURSE_KIT_SLIDE_UPDATED") >= 1)
check("delete_slide uses COURSE_KIT_SLIDE_DELETED",
      count_event(router_src, "COURSE_KIT_SLIDE_DELETED") >= 1)
check("reorder_slides uses COURSE_KIT_SLIDES_REORDERED",
      count_event(router_src, "COURSE_KIT_SLIDES_REORDERED") >= 1)
check("add_quizlet uses COURSE_KIT_QUIZLET_ADDED",
      count_event(router_src, "COURSE_KIT_QUIZLET_ADDED") >= 1)
check("update_quizlet uses COURSE_KIT_QUIZLET_UPDATED",
      count_event(router_src, "COURSE_KIT_QUIZLET_UPDATED") >= 1)
check("delete_quizlet uses COURSE_KIT_QUIZLET_DELETED",
      count_event(router_src, "COURSE_KIT_QUIZLET_DELETED") >= 1)
check("add_assignment uses COURSE_KIT_ASSIGNMENT_ADDED",
      count_event(router_src, "COURSE_KIT_ASSIGNMENT_ADDED") >= 1)
check("update_assignment uses COURSE_KIT_ASSIGNMENT_UPDATED",
      count_event(router_src, "COURSE_KIT_ASSIGNMENT_UPDATED") >= 1)
check("delete_assignment uses COURSE_KIT_ASSIGNMENT_DELETED",
      count_event(router_src, "COURSE_KIT_ASSIGNMENT_DELETED") >= 1)

# generate endpoint still uses GENERATION_QUEUED (correct — it IS a generation)
check("generate endpoint still uses COURSE_KIT_GENERATION_QUEUED",
      count_event(router_src, "COURSE_KIT_GENERATION_QUEUED") >= 1)

# No placeholder comment remnants
check("no 'reuse until STEP-08' comments remain",
      "reuse until STEP-08" not in router_src)

# ---------------------------------------------------------------------------
# 4. Router still imports and has 26 routes (no route count regression)
# ---------------------------------------------------------------------------
print("\n--- Router import + route count ---")
try:
    from app.modules.m03_course_kit.router import router
    from fastapi import APIRouter
    check("router imports cleanly after STEP-08 edits", True)
except Exception as exc:
    check(f"router import failed: {exc}", False)
    sys.exit(1)

check("router still has exactly 26 routes", len(router.routes) == 26)

# ---------------------------------------------------------------------------
# 5. Event groups: 22 total M03 events counted in enum
# ---------------------------------------------------------------------------
print("\n--- M03 event group counts ---")
all_events = [e.value for e in AuditEventType if e.value.startswith("COURSE_KIT_")]
check(f"total COURSE_KIT_* events == 22 (found {len(all_events)})",
      len(all_events) == 22)

lifecycle_events = [e for e in all_events if e in (
    "COURSE_KIT_CREATED", "COURSE_KIT_UPDATED", "COURSE_KIT_DELETED",
)]
check("3 lifecycle events", len(lifecycle_events) == 3)

generation_events = [e for e in all_events if "GENERATION" in e]
check("3 generation events", len(generation_events) == 3)

state_events = [e for e in all_events if e in (
    "COURSE_KIT_PUBLISHED", "COURSE_KIT_ARCHIVED", "COURSE_KIT_FORKED",
)]
check("3 state transition events", len(state_events) == 3)

slide_events = [e for e in all_events if "SLIDE" in e]
check("4 slide events", len(slide_events) == 4)

quizlet_events = [e for e in all_events if "QUIZLET" in e]
check("3 quizlet events", len(quizlet_events) == 3)

assignment_events = [e for e in all_events if "ASSIGNMENT" in e]
check("3 assignment events", len(assignment_events) == 3)

export_events = [e for e in all_events if "EXPORT" in e]
check("3 export events (for STEP-11)", len(export_events) == 3)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-08 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-08 smoke tests green.")
