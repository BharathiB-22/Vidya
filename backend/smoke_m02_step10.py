"""
Smoke tests for STEP-10: M02 router import + endpoint registration.
Run from backend/:  python smoke_m02_step10.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL",      "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",         "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",        "dummy_secret_for_smoke_test_only_32ch!")
os.environ.setdefault("S3_ENDPOINT",       "http://localhost:9000")
os.environ.setdefault("S3_BUCKET",         "dummy")
os.environ.setdefault("GEMINI_API_KEY",    "dummy")
os.environ.setdefault("ENVIRONMENT",       "development")

# ---------------------------------------------------------------------------
# 1. Import guard
# ---------------------------------------------------------------------------
from app.modules.m02_syllabus.router import router, _WRITE, _READ, _LOCK, _EXPORT, _err
from fastapi import APIRouter
from app.core.auth.models import TenantRole
print("PASS 1: router imports cleanly")

# ---------------------------------------------------------------------------
# 2. Router type + tag
# ---------------------------------------------------------------------------
assert isinstance(router, APIRouter), "router must be an APIRouter instance"
assert "syllabi" in router.tags, f"Expected tag 'syllabi', got {router.tags}"
print("PASS 2: router is APIRouter with tag='syllabi'")

# ---------------------------------------------------------------------------
# 3. RBAC role sets
# ---------------------------------------------------------------------------
assert TenantRole.ADMIN   in _WRITE  and TenantRole.FACULTY in _WRITE,  "_WRITE missing roles"
assert TenantRole.DEAN    not in _WRITE,                                 "_WRITE must not include DEAN"
assert TenantRole.ADMIN   in _READ   and TenantRole.DEAN in _READ,      "_READ missing roles"
assert TenantRole.ADMIN   in _LOCK   and TenantRole.DEAN in _LOCK,      "_LOCK missing roles"
assert TenantRole.FACULTY not in _LOCK,                                   "_LOCK must not include FACULTY"
assert TenantRole.ADMIN   in _EXPORT and TenantRole.FACULTY in _EXPORT, "_EXPORT missing roles"
print("PASS 3: RBAC role sets correct")

# ---------------------------------------------------------------------------
# 4. _err() maps SyllabusServiceError -> HTTPException
# ---------------------------------------------------------------------------
from fastapi import HTTPException
from app.modules.m02_syllabus.service import SyllabusServiceError

exc = _err(SyllabusServiceError("TEST_CODE", "test message", 409))
assert isinstance(exc, HTTPException),     "_err must return HTTPException"
assert exc.status_code == 409,             f"status_code mismatch: {exc.status_code}"
assert exc.detail["error"]   == "TEST_CODE",    f"detail.error mismatch: {exc.detail}"
assert exc.detail["message"] == "test message", f"detail.message mismatch: {exc.detail}"
print("PASS 4: _err() maps SyllabusServiceError -> HTTPException correctly")

# ---------------------------------------------------------------------------
# 5. Endpoint count + key paths
# ---------------------------------------------------------------------------
routes = {(r.path, list(r.methods)[0] if r.methods else "?"): True for r in router.routes}

EXPECTED = [
    # Syllabus CRUD
    ("",          "POST"),
    ("",          "GET"),
    ("/{syllabus_id}",          "GET"),
    ("/{syllabus_id}",          "PATCH"),
    ("/{syllabus_id}",          "DELETE"),
    ("/{syllabus_id}/status",   "GET"),
    ("/{syllabus_id}/versions", "GET"),
    # AI generation
    ("/{syllabus_id}/generate",        "POST"),
    ("/{syllabus_id}/jobs/{job_id}",   "GET"),
    # State transitions
    ("/{syllabus_id}/approve", "POST"),
    ("/{syllabus_id}/reject",  "POST"),
    ("/{syllabus_id}/lock",    "POST"),
    ("/{syllabus_id}/unlock",  "POST"),
    ("/{syllabus_id}/fork",    "POST"),
    # Compliance
    ("/{syllabus_id}/compliance", "GET"),
    # Course outcomes
    ("/{syllabus_id}/outcomes",            "GET"),
    ("/{syllabus_id}/outcomes",            "POST"),
    ("/{syllabus_id}/outcomes/{co_id}",    "PATCH"),
    ("/{syllabus_id}/outcomes/{co_id}",    "DELETE"),
    # CO-PO mappings
    ("/{syllabus_id}/outcomes/{co_id}/mappings", "PUT"),
    ("/{syllabus_id}/copo-matrix",               "GET"),
    # Units
    ("/{syllabus_id}/units",              "GET"),
    ("/{syllabus_id}/units",              "POST"),
    ("/{syllabus_id}/units/{unit_id}",    "PATCH"),
    ("/{syllabus_id}/units/{unit_id}",    "DELETE"),
    ("/{syllabus_id}/units/reorder",      "PUT"),
    # References
    ("/{syllabus_id}/references/search",         "GET"),
    ("/{syllabus_id}/references",                "GET"),
    ("/{syllabus_id}/references",                "POST"),
    ("/{syllabus_id}/references/{ref_id}",       "PATCH"),
    ("/{syllabus_id}/references/{ref_id}",       "DELETE"),
    ("/{syllabus_id}/references/{ref_id}/confirm", "POST"),
    # Export
    ("/{syllabus_id}/export", "POST"),
]

all_paths  = [(r.path, m) for r in router.routes for m in (r.methods or [])]
missing    = []
for path, method in EXPECTED:
    if (path, method) not in all_paths:
        missing.append(f"{method} {path}")

if missing:
    print("FAIL 5: missing endpoints:")
    for m in missing:
        print(f"  - {m}")
    sys.exit(1)

print(f"PASS 5: all {len(EXPECTED)} expected endpoints registered")
actual_count = len(all_paths)
print(f"       (total routes on router: {actual_count})")

# ---------------------------------------------------------------------------
# 6. Audit event types used in router are valid
# ---------------------------------------------------------------------------
from app.core.audit_log.models import AuditEventType

USED_EVENTS = [
    "SYLLABUS_CREATED", "SYLLABUS_UPDATED", "SYLLABUS_DELETED",
    "SYLLABUS_GENERATION_QUEUED",
    "SYLLABUS_APPROVED", "SYLLABUS_REJECTED", "SYLLABUS_LOCKED",
    "SYLLABUS_UNLOCKED", "SYLLABUS_FORKED",
    "SYLLABUS_CO_ADDED", "SYLLABUS_CO_UPDATED", "SYLLABUS_CO_DELETED",
    "SYLLABUS_COPO_MAPPING_UPDATED",
    "SYLLABUS_UNIT_ADDED", "SYLLABUS_UNIT_UPDATED", "SYLLABUS_UNIT_DELETED",
    "SYLLABUS_REFERENCE_ADDED", "SYLLABUS_REFERENCE_UPDATED",
    "SYLLABUS_REFERENCE_DELETED", "SYLLABUS_REFERENCE_CONFIRMED",
    "SYLLABUS_EXPORT_REQUESTED",
]
bad = [e for e in USED_EVENTS if not hasattr(AuditEventType, e)]
assert not bad, f"Unknown AuditEventType members: {bad}"
print(f"PASS 6: all {len(USED_EVENTS)} audit event types used in router are valid")

# ---------------------------------------------------------------------------
# 7. /references/search declared before /{ref_id} (routing order safety)
# ---------------------------------------------------------------------------
paths_ordered = [r.path for r in router.routes]
search_idx = next((i for i, p in enumerate(paths_ordered) if p.endswith("/references/search")), None)
refid_idx  = next((i for i, p in enumerate(paths_ordered) if p.endswith("/references/{ref_id}")), None)
assert search_idx is not None, "/references/search endpoint not found"
assert refid_idx  is not None, "/references/{ref_id} endpoint not found"
assert search_idx < refid_idx, (
    f"/references/search (idx {search_idx}) must be declared before "
    f"/references/{{ref_id}} (idx {refid_idx})"
)
print("PASS 7: /references/search declared before /references/{ref_id}")

print("\nAll smoke tests passed. STEP-10 router is correct.")
