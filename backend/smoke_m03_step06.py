"""
Smoke tests for STEP-06: M03 Celery task + service dispatch.

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step06.py
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
# 1. Audit event additions
# ---------------------------------------------------------------------------
print("\n--- AuditEventType additions ---")
try:
    from app.core.audit_log.models import AuditEventType
    check("COURSE_KIT_GENERATION_QUEUED exists",
          hasattr(AuditEventType, "COURSE_KIT_GENERATION_QUEUED"))
    check("COURSE_KIT_GENERATION_COMPLETED exists",
          hasattr(AuditEventType, "COURSE_KIT_GENERATION_COMPLETED"))
    check("COURSE_KIT_GENERATION_FAILED exists",
          hasattr(AuditEventType, "COURSE_KIT_GENERATION_FAILED"))
    check("COURSE_KIT_GENERATION_COMPLETED value is correct string",
          AuditEventType.COURSE_KIT_GENERATION_COMPLETED == "COURSE_KIT_GENERATION_COMPLETED")
except Exception as exc:
    check(f"AuditEventType import failed: {exc}", False)
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Celery task module imports cleanly
# ---------------------------------------------------------------------------
print("\n--- Celery task module ---")
try:
    from app.workers.heavy.course_kit_generation import generate_course_kit, _run_generation
    check("course_kit_generation module imports cleanly", True)
except Exception as exc:
    check(f"course_kit_generation import failed: {exc}", False)
    sys.exit(1)

check("generate_course_kit is a Celery task",
      hasattr(generate_course_kit, "delay"))
check("generate_course_kit has correct name",
      generate_course_kit.name == "app.workers.heavy.generate_course_kit")
check("generate_course_kit has max_retries=3",
      generate_course_kit.max_retries == 3)
check("_run_generation is a coroutine function",
      inspect.iscoroutinefunction(_run_generation))

# ---------------------------------------------------------------------------
# 3. Task is registered in celery_app include list
# ---------------------------------------------------------------------------
print("\n--- celery_app include list ---")
from app.workers.celery_app import celery_app
check("course_kit_generation is in celery_app include",
      "app.workers.heavy.course_kit_generation" in celery_app.conf.include)

# ---------------------------------------------------------------------------
# 4. Task routes to heavy queue
# ---------------------------------------------------------------------------
print("\n--- Queue routing ---")
routes = celery_app.conf.task_routes or {}
# The wildcard route "app.workers.heavy.*" covers the new task.
heavy_route = routes.get("app.workers.heavy.*", {})
check("heavy tasks route to celery-heavy queue",
      heavy_route.get("queue") == "celery-heavy")

# ---------------------------------------------------------------------------
# 5. Service module imports cleanly
# ---------------------------------------------------------------------------
print("\n--- Service module ---")
try:
    from app.modules.m03_course_kit.service import (
        CourseKitService,
        KitServiceError,
    )
    check("service module imports cleanly", True)
except Exception as exc:
    check(f"service module import failed: {exc}", False)
    sys.exit(1)

check("KitServiceError is an Exception subclass",
      issubclass(KitServiceError, Exception))
check("KitServiceError has code/message/status_code",
      all(hasattr(KitServiceError("X", "msg", 400), attr)
          for attr in ("code", "message", "status_code")))
check("CourseKitService.dispatch_kit_generation exists",
      hasattr(CourseKitService, "dispatch_kit_generation"))
check("dispatch_kit_generation is a coroutine function",
      inspect.iscoroutinefunction(CourseKitService.dispatch_kit_generation))

# ---------------------------------------------------------------------------
# 6. dispatch_kit_generation signature has required parameters
# ---------------------------------------------------------------------------
print("\n--- dispatch_kit_generation signature ---")
sig = inspect.signature(CourseKitService.dispatch_kit_generation)
params = set(sig.parameters.keys())
check("dispatch signature: kit_id param",      "kit_id"      in params)
check("dispatch signature: tenant_id param",   "tenant_id"   in params)
check("dispatch signature: schema_name param", "schema_name" in params)
check("dispatch signature: db param",          "db"          in params)

# ---------------------------------------------------------------------------
# 7. KitServiceError carries expected attributes
# ---------------------------------------------------------------------------
print("\n--- KitServiceError attributes ---")
err = KitServiceError("NOT_FOUND", "Kit missing.", 404)
check("code attribute correct",        err.code        == "NOT_FOUND")
check("message attribute correct",     err.message     == "Kit missing.")
check("status_code attribute correct", err.status_code == 404)

# ---------------------------------------------------------------------------
# 8. _run_generation accepts expected keyword arguments
# ---------------------------------------------------------------------------
print("\n--- _run_generation signature ---")
run_sig = inspect.signature(_run_generation)
run_params = set(run_sig.parameters.keys())
check("_run_generation: kit_id param",     "kit_id"     in run_params)
check("_run_generation: tenant_id param",  "tenant_id"  in run_params)
check("_run_generation: schema_name param","schema_name" in run_params)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-06 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-06 smoke tests green.")
