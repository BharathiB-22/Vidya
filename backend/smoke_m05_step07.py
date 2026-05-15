"""STEP-07 smoke tests -- M05 repository layer.

Inspect-based: verifies method existence, async signatures, keyword-only db
param, and key ORM patterns. No real database connection required.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import inspect
import os

os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from app.modules.m05_learning_materials.repository import (
    LearningPackageRepository,
    PackageItemRepository,
    PackageQARepository,
)
from app.modules.m05_learning_materials.models import (
    LearningPackage,
    PackageItem,
    PackageQASession,
    PackageQAMessage,
    PackageStatus,
    MaterialSourceType,
    QARole,
)

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


def has_async(cls, method: str) -> bool:
    fn = getattr(cls, method, None)
    return fn is not None and inspect.iscoroutinefunction(fn)


def has_kw_db(cls, method: str) -> bool:
    fn = getattr(cls, method, None)
    if fn is None:
        return False
    sig = inspect.signature(fn)
    p = sig.parameters.get("db")
    return p is not None and p.kind == inspect.Parameter.KEYWORD_ONLY


def src(cls, method: str) -> str:
    return inspect.getsource(getattr(cls, method))


# ===========================================================================
# 1. Import contract
# ===========================================================================
print("\n--- imports ---")

check("LearningPackageRepository importable", inspect.isclass(LearningPackageRepository))
check("PackageItemRepository importable",     inspect.isclass(PackageItemRepository))
check("PackageQARepository importable",       inspect.isclass(PackageQARepository))

# ===========================================================================
# 2. LearningPackageRepository -- method existence and async
# ===========================================================================
print("\n--- LearningPackageRepository methods ---")

LP_WRITE = ["create", "update_status", "set_curating", "set_ready",
            "set_qdrant_indexed", "mark_outdated_by_syllabus"]
LP_READ  = ["get_by_id", "get_by_syllabus_unit", "list_by_syllabus"]

for method in LP_WRITE + LP_READ:
    check(f"LP.{method} exists and is async", has_async(LearningPackageRepository, method))

for method in LP_WRITE + LP_READ:
    check(f"LP.{method} has keyword-only db", has_kw_db(LearningPackageRepository, method))

# ===========================================================================
# 3. LearningPackageRepository -- ORM patterns
# ===========================================================================
print("\n--- LearningPackageRepository ORM patterns ---")

check("LP.update_status uses .returning()",
      ".returning(" in src(LearningPackageRepository, "update_status"))

check("LP.set_curating sets status=CURATING",
      "CURATING" in src(LearningPackageRepository, "set_curating"))

check("LP.set_curating uses .returning()",
      ".returning(" in src(LearningPackageRepository, "set_curating"))

check("LP.set_ready sets status=READY and curated_at",
      "READY" in src(LearningPackageRepository, "set_ready")
      and "curated_at" in src(LearningPackageRepository, "set_ready"))

check("LP.set_ready uses .returning()",
      ".returning(" in src(LearningPackageRepository, "set_ready"))

check("LP.set_qdrant_indexed sets qdrant_indexed=True",
      "qdrant_indexed" in src(LearningPackageRepository, "set_qdrant_indexed")
      and ".returning(" in src(LearningPackageRepository, "set_qdrant_indexed"))

check("LP.mark_outdated_by_syllabus bulk-updates READY -> OUTDATED",
      "OUTDATED" in src(LearningPackageRepository, "mark_outdated_by_syllabus")
      and "READY" in src(LearningPackageRepository, "mark_outdated_by_syllabus"))

check("LP.mark_outdated_by_syllabus returns rowcount (int)",
      "rowcount" in src(LearningPackageRepository, "mark_outdated_by_syllabus"))

check("LP.get_by_syllabus_unit filters out OUTDATED",
      "OUTDATED" in src(LearningPackageRepository, "get_by_syllabus_unit"))

check("LP.get_by_syllabus_unit orders by version desc",
      "version" in src(LearningPackageRepository, "get_by_syllabus_unit")
      and "desc" in src(LearningPackageRepository, "get_by_syllabus_unit"))

check("LP.list_by_syllabus supports status_filter kwarg",
      "status_filter" in src(LearningPackageRepository, "list_by_syllabus"))

check("LP.list_by_syllabus orders by unit_number asc",
      "unit_number" in src(LearningPackageRepository, "list_by_syllabus")
      and "asc" in src(LearningPackageRepository, "list_by_syllabus"))

check("LP.create initialises status=PENDING",
      "PENDING" in src(LearningPackageRepository, "create"))

# ===========================================================================
# 4. PackageItemRepository -- method existence and async
# ===========================================================================
print("\n--- PackageItemRepository methods ---")

PI_WRITE = ["bulk_create", "update_relevance_score", "set_qdrant_indexed",
            "delete_all_for_package"]
PI_READ  = ["get_by_id", "list_by_package", "dedup_hash_exists"]

for method in PI_WRITE + PI_READ:
    check(f"PI.{method} exists and is async", has_async(PackageItemRepository, method))

for method in PI_WRITE + PI_READ:
    check(f"PI.{method} has keyword-only db", has_kw_db(PackageItemRepository, method))

# ===========================================================================
# 5. PackageItemRepository -- ORM patterns
# ===========================================================================
print("\n--- PackageItemRepository ORM patterns ---")

check("PI.bulk_create uses db.add_all()",
      "add_all" in src(PackageItemRepository, "bulk_create"))

check("PI.bulk_create handles metadata_ attribute name",
      "metadata_" in src(PackageItemRepository, "bulk_create"))

check("PI.bulk_create preserves display_order",
      "display_order" in src(PackageItemRepository, "bulk_create"))

check("PI.bulk_create handles faculty_recommended",
      "faculty_recommended" in src(PackageItemRepository, "bulk_create"))

check("PI.update_relevance_score uses .returning()",
      ".returning(" in src(PackageItemRepository, "update_relevance_score"))

check("PI.update_relevance_score updates display_order too",
      "display_order" in src(PackageItemRepository, "update_relevance_score"))

check("PI.delete_all_for_package uses delete() and returns rowcount",
      "delete(" in src(PackageItemRepository, "delete_all_for_package")
      and "rowcount" in src(PackageItemRepository, "delete_all_for_package"))

check("PI.dedup_hash_exists uses func.count and content_hash",
      "func.count" in src(PackageItemRepository, "dedup_hash_exists")
      and "content_hash" in src(PackageItemRepository, "dedup_hash_exists"))

check("PI.list_by_package orders by display_order asc",
      "display_order" in src(PackageItemRepository, "list_by_package")
      and "asc" in src(PackageItemRepository, "list_by_package"))

check("PI.list_by_package supports faculty_only filter",
      "faculty_only" in src(PackageItemRepository, "list_by_package"))

# ===========================================================================
# 6. PackageQARepository -- method existence and async
# ===========================================================================
print("\n--- PackageQARepository methods ---")

QA_WRITE = ["create_session", "append_message"]
QA_READ  = ["get_session", "get_session_with_messages",
            "list_messages", "list_sessions_for_student"]

for method in QA_WRITE + QA_READ:
    check(f"QA.{method} exists and is async", has_async(PackageQARepository, method))

for method in QA_WRITE + QA_READ:
    check(f"QA.{method} has keyword-only db", has_kw_db(PackageQARepository, method))

# ===========================================================================
# 7. PackageQARepository -- ORM patterns
# ===========================================================================
print("\n--- PackageQARepository ORM patterns ---")

check("QA.append_message touches parent session updated_at",
      "updated_at" in src(PackageQARepository, "append_message")
      and "PackageQASession" in src(PackageQARepository, "append_message"))

check("QA.append_message defaults sources to []",
      "sources" in src(PackageQARepository, "append_message")
      and "[]" in src(PackageQARepository, "append_message"))

check("QA.list_messages orders by created_at asc (chronological)",
      "created_at" in src(PackageQARepository, "list_messages")
      and "asc" in src(PackageQARepository, "list_messages"))

check("QA.get_session_with_messages uses selectinload",
      "selectinload" in src(PackageQARepository, "get_session_with_messages"))

check("QA.list_sessions_for_student orders by created_at desc (newest first)",
      "created_at" in src(PackageQARepository, "list_sessions_for_student")
      and "desc" in src(PackageQARepository, "list_sessions_for_student"))

# ===========================================================================
# 8. All @staticmethod (matches M03 convention)
# ===========================================================================
print("\n--- @staticmethod convention ---")

all_methods = {
    LearningPackageRepository: LP_WRITE + LP_READ,
    PackageItemRepository:     PI_WRITE + PI_READ,
    PackageQARepository:       QA_WRITE + QA_READ,
}
for cls, methods in all_methods.items():
    for method in methods:
        raw = cls.__dict__.get(method)
        check(
            f"{cls.__name__}.{method} is @staticmethod",
            isinstance(raw, staticmethod),
        )

# ===========================================================================
# 9. Enum/model references (no typos)
# ===========================================================================
print("\n--- enum references ---")

check("PackageStatus enum accessible", hasattr(PackageStatus, "PENDING"))
check("PackageStatus.CURATING exists", hasattr(PackageStatus, "CURATING"))
check("PackageStatus.READY exists",    hasattr(PackageStatus, "READY"))
check("PackageStatus.OUTDATED exists", hasattr(PackageStatus, "OUTDATED"))
check("MaterialSourceType enum accessible", hasattr(MaterialSourceType, "YOUTUBE"))
check("QARole.USER exists",            hasattr(QARole, "USER"))
check("QARole.ASSISTANT exists",       hasattr(QARole, "ASSISTANT"))

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*52}")
print(f"STEP-07 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before proceeding.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-07 smoke tests green.")
