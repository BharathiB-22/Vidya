"""
Smoke tests for STEP-11: main.py wiring + Celery autodiscovery.
Run from backend/:  python smoke_m02_step11.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "dummy_secret_for_smoke_test_only_32ch!")
os.environ.setdefault("S3_ENDPOINT",    "http://localhost:9000")
os.environ.setdefault("S3_BUCKET",      "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("ENVIRONMENT",    "development")

# ---------------------------------------------------------------------------
# 1. main.py imports without error
# ---------------------------------------------------------------------------
import app.main as main_mod
print("PASS 1: app.main imports cleanly")

# ---------------------------------------------------------------------------
# 2. FastAPI app object exists
# ---------------------------------------------------------------------------
from fastapi import FastAPI
assert isinstance(main_mod.app, FastAPI), "main_mod.app must be a FastAPI instance"
print("PASS 2: FastAPI app object present")

# ---------------------------------------------------------------------------
# 3. M02 syllabus router is included at /syllabi
# ---------------------------------------------------------------------------
from app.modules.m02_syllabus.router import router as syllabus_router

syllabi_routes = [
    r for r in main_mod.app.routes
    if getattr(r, "path", "").startswith("/syllabi")
]
assert len(syllabi_routes) > 0, "No routes found under /syllabi prefix"
print(f"PASS 3: {len(syllabi_routes)} routes registered under /syllabi")

# ---------------------------------------------------------------------------
# 4. Spot-check key M02 full paths on the app
# ---------------------------------------------------------------------------
all_paths = [(r.path, m) for r in main_mod.app.routes for m in (getattr(r, "methods", None) or [])]

KEY_PATHS = [
    ("/syllabi",                          "POST"),
    ("/syllabi",                          "GET"),
    ("/syllabi/{syllabus_id}",            "GET"),
    ("/syllabi/{syllabus_id}/generate",   "POST"),
    ("/syllabi/{syllabus_id}/approve",    "POST"),
    ("/syllabi/{syllabus_id}/lock",       "POST"),
    ("/syllabi/{syllabus_id}/copo-matrix","GET"),
    ("/syllabi/{syllabus_id}/export",     "POST"),
    ("/syllabi/{syllabus_id}/references/search", "GET"),
]
missing = [(p, m) for p, m in KEY_PATHS if (p, m) not in all_paths]
assert not missing, f"Missing routes on app: {missing}"
print(f"PASS 4: all {len(KEY_PATHS)} key full paths present on app")

# ---------------------------------------------------------------------------
# 5. M01 program routes still intact (regression guard)
# ---------------------------------------------------------------------------
program_routes = [r for r in main_mod.app.routes if getattr(r, "path", "").startswith("/programs")]
assert len(program_routes) > 0, "M01 /programs routes missing — regression!"
print(f"PASS 5: M01 /programs routes intact ({len(program_routes)} routes)")

# ---------------------------------------------------------------------------
# 6. Celery autodiscovery — both M02 tasks in the include list
# ---------------------------------------------------------------------------
from app.workers.celery_app import celery_app

include = celery_app.conf.include
assert "app.workers.heavy.syllabus_generation"  in include, "syllabus_generation missing from Celery include"
assert "app.workers.heavy.reference_enrichment" in include, "reference_enrichment missing from Celery include"
print("PASS 6: both M02 Celery tasks in autodiscovery include list")

# ---------------------------------------------------------------------------
# 7. Heavy-queue routing rule covers M02 task names
# ---------------------------------------------------------------------------
routes = celery_app.conf.task_routes
assert "app.workers.heavy.*" in routes, "heavy queue routing rule missing"
assert routes["app.workers.heavy.*"]["queue"] == "celery-heavy", "wrong queue name"
print("PASS 7: app.workers.heavy.* routes to celery-heavy queue")

# ---------------------------------------------------------------------------
# 8. No circular imports — re-import key modules to confirm
# ---------------------------------------------------------------------------
import importlib
for mod_name in [
    "app.modules.m02_syllabus.models",
    "app.modules.m02_syllabus.schemas",
    "app.modules.m02_syllabus.repository",
    "app.modules.m02_syllabus.service",
    "app.modules.m02_syllabus.router",
    "app.workers.heavy.syllabus_generation",
    "app.workers.heavy.reference_enrichment",
]:
    importlib.import_module(mod_name)
print("PASS 8: no circular imports across all M02 modules")

print("\nAll smoke tests passed. STEP-11 wiring is correct.")
