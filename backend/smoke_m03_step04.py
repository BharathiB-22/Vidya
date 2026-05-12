"""STEP-04 smoke tests — M03 repository layer."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",    "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",   "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import inspect
from uuid import UUID

from app.modules.m03_course_kit.repository import (
    CourseKitRepository,
    SlideRepository,
    QuizletRepository,
    AssignmentRepository,
    TaskJobPublicRepository,   # re-exported from M02
)

# ---------------------------------------------------------------------------
# 1. All 5 repository classes importable
# ---------------------------------------------------------------------------
for cls in (CourseKitRepository, SlideRepository, QuizletRepository,
            AssignmentRepository, TaskJobPublicRepository):
    assert inspect.isclass(cls), f"{cls} is not a class"

# ---------------------------------------------------------------------------
# 2. CourseKitRepository — required methods present and async
# ---------------------------------------------------------------------------
ck_write = ["create", "update", "update_status", "set_published",
            "set_ai_generating", "reset_to_draft", "delete"]
ck_read  = ["get_by_id", "get_detail", "list_by_syllabus", "count_by_syllabus",
            "list_versions", "get_published_for_unit", "has_published_for_unit",
            "get_next_version"]

for method in ck_write + ck_read:
    fn = getattr(CourseKitRepository, method, None)
    assert fn is not None,               f"CourseKitRepository.{method} missing"
    assert inspect.iscoroutinefunction(fn), f"CourseKitRepository.{method} not async"

# ---------------------------------------------------------------------------
# 3. SlideRepository — required methods present and async
# ---------------------------------------------------------------------------
slide_methods = ["create", "bulk_create", "update", "delete", "delete_all",
                 "reorder", "get_by_id", "get_by_number", "list_by_kit", "count_by_kit"]

for method in slide_methods:
    fn = getattr(SlideRepository, method, None)
    assert fn is not None,               f"SlideRepository.{method} missing"
    assert inspect.iscoroutinefunction(fn), f"SlideRepository.{method} not async"

# ---------------------------------------------------------------------------
# 4. QuizletRepository — required methods present and async
# ---------------------------------------------------------------------------
quizlet_methods = ["create", "bulk_create", "update", "delete", "delete_all",
                   "get_by_id", "list_by_kit", "count_by_kit"]

for method in quizlet_methods:
    fn = getattr(QuizletRepository, method, None)
    assert fn is not None,               f"QuizletRepository.{method} missing"
    assert inspect.iscoroutinefunction(fn), f"QuizletRepository.{method} not async"

# ---------------------------------------------------------------------------
# 5. AssignmentRepository — required methods present and async
# ---------------------------------------------------------------------------
assign_methods = ["create", "bulk_create", "update", "delete", "delete_all",
                  "get_by_id", "list_by_kit", "list_by_kit_and_type", "count_by_kit"]

for method in assign_methods:
    fn = getattr(AssignmentRepository, method, None)
    assert fn is not None,               f"AssignmentRepository.{method} missing"
    assert inspect.iscoroutinefunction(fn), f"AssignmentRepository.{method} not async"

# ---------------------------------------------------------------------------
# 6. TaskJobPublicRepository is the M02 class (not a copy)
# ---------------------------------------------------------------------------
from app.modules.m02_syllabus.repository import TaskJobPublicRepository as M02Repo
assert TaskJobPublicRepository is M02Repo, "TaskJobPublicRepository must be the same object as M02's"

# ---------------------------------------------------------------------------
# 7. All write methods use keyword-only db param (architectural contract)
# ---------------------------------------------------------------------------
def _has_kw_db(fn) -> bool:
    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        if name == "db" and param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True
    return False

for repo_cls, methods in [
    (CourseKitRepository, ck_write + ck_read),
    (SlideRepository,     slide_methods),
    (QuizletRepository,   quizlet_methods),
    (AssignmentRepository, assign_methods),
]:
    for method in methods:
        fn = getattr(repo_cls, method)
        assert _has_kw_db(fn), f"{repo_cls.__name__}.{method} missing keyword-only `db` param"

# ---------------------------------------------------------------------------
# 8. CourseKitRepository.get_detail uses selectinload (eager loading)
# ---------------------------------------------------------------------------
import ast, textwrap
src = inspect.getsource(CourseKitRepository.get_detail)
assert "selectinload" in src, "get_detail must use selectinload for eager loading"
assert "slides" in src
assert "quizlets" in src
assert "assignments" in src

# ---------------------------------------------------------------------------
# 9. status-transition methods use .returning(CourseKit)
# ---------------------------------------------------------------------------
for method in ("update_status", "set_published", "set_ai_generating", "reset_to_draft"):
    src = inspect.getsource(getattr(CourseKitRepository, method))
    assert ".returning(" in src, f"{method} must use .returning() for efficiency"

# ---------------------------------------------------------------------------
# 10. bulk_create methods use db.add_all (not looped db.add)
# ---------------------------------------------------------------------------
for repo_cls in (SlideRepository, QuizletRepository, AssignmentRepository,
                 CourseKitRepository):
    if hasattr(repo_cls, "bulk_create"):
        src = inspect.getsource(repo_cls.bulk_create)
        assert "add_all" in src, f"{repo_cls.__name__}.bulk_create must use db.add_all"

print("STEP-04: all 10 assertions passed.")
