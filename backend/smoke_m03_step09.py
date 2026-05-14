"""
Smoke tests for STEP-09: main.py wiring + Celery autodiscovery.

Run from backend/:
    $env:PYTHONPATH="."
    $env:DATABASE_URL="postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya"
    $env:JWT_SECRET="test"
    $env:GROQ_API_KEY="test"
    python smoke_m03_step09.py
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
# 1. FastAPI app imports cleanly (no circular imports, no startup side-effects)
# ---------------------------------------------------------------------------
print("\n--- FastAPI app import ---")
try:
    from app.main import app
    check("app.main imports cleanly", True)
except Exception as exc:
    check(f"app.main import failed: {exc}", False)
    sys.exit(1)

from fastapi import FastAPI
check("app is a FastAPI instance", isinstance(app, FastAPI))

# ---------------------------------------------------------------------------
# 2. M03 router is registered at /course-kits
# ---------------------------------------------------------------------------
print("\n--- M03 router registration ---")
all_paths = [getattr(r, "path", "") for r in app.routes]

check("/course-kits prefix registered",
      any(p.startswith("/course-kits") for p in all_paths))

# Spot-check specific M03 routes
check("POST /course-kits registered",
      "/course-kits" in all_paths)
check("GET  /course-kits/{kit_id} registered",
      "/course-kits/{kit_id}" in all_paths)
check("POST /course-kits/{kit_id}/generate registered",
      "/course-kits/{kit_id}/generate" in all_paths)
check("POST /course-kits/{kit_id}/publish registered",
      "/course-kits/{kit_id}/publish" in all_paths)
check("GET  /course-kits/{kit_id}/slides registered",
      "/course-kits/{kit_id}/slides" in all_paths)
check("GET  /course-kits/{kit_id}/quizlets registered",
      "/course-kits/{kit_id}/quizlets" in all_paths)
check("GET  /course-kits/{kit_id}/assignments registered",
      "/course-kits/{kit_id}/assignments" in all_paths)

# Count: M03 adds 26 routes; check total route count >= previous count + 26
m03_paths = [p for p in all_paths if p.startswith("/course-kits")]
check(f"26 routes under /course-kits (found {len(m03_paths)})",
      len(m03_paths) == 26)

# ---------------------------------------------------------------------------
# 3. M01 / M02 routes unaffected
# ---------------------------------------------------------------------------
print("\n--- M01/M02 route regression ---")
check("M01 /programs prefix still registered",
      any(p.startswith("/programs") for p in all_paths))
check("M02 /syllabi prefix still registered",
      any(p.startswith("/syllabi") for p in all_paths))
check("Auth /auth prefix still registered",
      any(p.startswith("/auth") for p in all_paths))

# ---------------------------------------------------------------------------
# 4. Celery autodiscovery includes M03 task
# ---------------------------------------------------------------------------
print("\n--- Celery autodiscovery ---")
try:
    from app.workers.celery_app import celery_app
    check("celery_app imports cleanly", True)
except Exception as exc:
    check(f"celery_app import failed: {exc}", False)
    sys.exit(1)

check("course_kit_generation in celery_app include",
      "app.workers.heavy.course_kit_generation" in celery_app.conf.include)

# Existing tasks not removed
check("syllabus_generation still in celery_app include",
      "app.workers.heavy.syllabus_generation" in celery_app.conf.include)
check("program_structure still in celery_app include",
      "app.workers.heavy.program_structure" in celery_app.conf.include)

# Route to heavy queue still wired
routes = celery_app.conf.task_routes or {}
heavy_route = routes.get("app.workers.heavy.*", {})
check("heavy tasks still route to celery-heavy queue",
      heavy_route.get("queue") == "celery-heavy")

# ---------------------------------------------------------------------------
# 5. M03 Celery task is importable independently
# ---------------------------------------------------------------------------
print("\n--- M03 Celery task ---")
try:
    from app.workers.heavy.course_kit_generation import generate_course_kit
    check("course_kit_generation task imports cleanly", True)
except Exception as exc:
    check(f"course_kit_generation import failed: {exc}", False)
    sys.exit(1)

check("generate_course_kit has .delay method",
      hasattr(generate_course_kit, "delay"))
check("generate_course_kit task name correct",
      generate_course_kit.name == "app.workers.heavy.generate_course_kit")

# ---------------------------------------------------------------------------
# 6. Module package structure is intact
# ---------------------------------------------------------------------------
print("\n--- M03 module package ---")
try:
    import app.modules.m03_course_kit as m03_pkg
    check("m03_course_kit package importable", True)
except Exception as exc:
    check(f"m03_course_kit package import failed: {exc}", False)
    sys.exit(1)

# All expected submodules importable without error
submodules = [
    "app.modules.m03_course_kit.models",
    "app.modules.m03_course_kit.schemas",
    "app.modules.m03_course_kit.repository",
    "app.modules.m03_course_kit.ai_provider",
    "app.modules.m03_course_kit.service",
    "app.modules.m03_course_kit.router",
]
for mod_name in submodules:
    try:
        __import__(mod_name)
        check(f"{mod_name.split('.')[-1]} submodule importable", True)
    except Exception as exc:
        check(f"{mod_name.split('.')[-1]} import failed: {exc}", False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*50}")
print(f"STEP-09 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before committing.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-09 smoke tests green.")
