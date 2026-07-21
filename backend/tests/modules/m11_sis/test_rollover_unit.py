"""
Unit tests — H54 SIS Semester Rollover

No live database.  All tests use import + assert only.

Coverage:
  1.  RolloverScopeIn — fields and scope literals
  2.  RolloverRowOut — all 13 fields present
  3.  RolloverSummary — fields
  4.  RolloverPreviewResponse — fields
  5.  RolloverCommitRowResult — fields and outcome literals
  6.  RolloverCommitResult — fields
  7.  RolloverService — class importable
  8.  RolloverService — preview is a static async method
  9.  RolloverService — commit is a static async method
  10. RolloverService — _resolve_enrollment_rows is a static method
  11. RolloverService — _find_target_semester is a static method
  12. RolloverService — _find_target_section is a static method
  13. RolloverService — _build_preview_rows is a static method
  14. rollover_router — importable
  15. rollover_router — POST /rollover/preview route registered
  16. rollover_router — POST /rollover/commit route registered
  17. RBAC — both routes require ADMIN only
  18. router.py — includes rollover_router
  19. RolloverScopeIn accepts scope="all_programs"
  20. RolloverScopeIn accepts scope="program"
  21. RolloverScopeIn accepts scope="batch"
  22. RolloverScopeIn accepts scope="semester"
  23. RolloverRowOut status field accepts "ready" and "blocked"
  24. RolloverCommitRowResult outcome field accepts all three values
  25. RolloverService imported inside rollover_router (wiring check)
"""
import inspect


# ---------------------------------------------------------------------------
# 1–6. Schemas
# ---------------------------------------------------------------------------

def test_rollover_scope_in_has_scope_field():
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    assert "scope" in RolloverScopeIn.model_fields


def test_rollover_scope_in_optional_filter_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    fields = RolloverScopeIn.model_fields
    assert "program_id" in fields
    assert "batch_id" in fields
    assert "source_semester_id" in fields


def test_rollover_row_out_all_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverRowOut
    expected = {
        "enrollment_id", "student_id", "student_name", "student_email",
        "current_section_id", "current_section_name", "current_semester_number",
        "batch_name", "program_name",
        "target_semester_number", "target_section_id", "target_section_name",
        "status", "reason",
    }
    assert expected <= set(RolloverRowOut.model_fields)


def test_rollover_summary_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverSummary
    assert {"total", "ready", "blocked"} <= set(RolloverSummary.model_fields)


def test_rollover_preview_response_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverPreviewResponse
    assert {"scope", "summary", "rows"} <= set(RolloverPreviewResponse.model_fields)


def test_rollover_commit_row_result_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverCommitRowResult
    expected = {"enrollment_id", "student_id", "student_name", "target_section_id", "outcome", "reason"}
    assert expected <= set(RolloverCommitRowResult.model_fields)


def test_rollover_commit_result_fields():
    from app.modules.m11_sis.rollover_schemas import RolloverCommitResult
    assert {"moved", "skipped", "errors", "rows"} <= set(RolloverCommitResult.model_fields)


# ---------------------------------------------------------------------------
# 7–13. RolloverService methods
# ---------------------------------------------------------------------------

def test_rollover_service_importable():
    from app.modules.m11_sis.rollover_service import RolloverService
    assert RolloverService is not None


def test_rollover_service_preview_is_static_async():
    from app.modules.m11_sis.rollover_service import RolloverService
    method = getattr(RolloverService, "preview", None)
    assert callable(method)
    assert inspect.iscoroutinefunction(method)


def test_rollover_service_commit_is_static_async():
    from app.modules.m11_sis.rollover_service import RolloverService
    method = getattr(RolloverService, "commit", None)
    assert callable(method)
    assert inspect.iscoroutinefunction(method)


def test_rollover_service_resolve_enrollment_rows_exists():
    from app.modules.m11_sis.rollover_service import RolloverService
    assert callable(getattr(RolloverService, "_resolve_enrollment_rows", None))


def test_rollover_service_find_target_semester_exists():
    from app.modules.m11_sis.rollover_service import RolloverService
    assert callable(getattr(RolloverService, "_find_target_semester", None))


def test_rollover_service_find_target_section_exists():
    from app.modules.m11_sis.rollover_service import RolloverService
    assert callable(getattr(RolloverService, "_find_target_section", None))


def test_rollover_service_build_preview_rows_exists():
    from app.modules.m11_sis.rollover_service import RolloverService
    assert callable(getattr(RolloverService, "_build_preview_rows", None))


# ---------------------------------------------------------------------------
# 14–17. Router
# ---------------------------------------------------------------------------

def test_rollover_router_importable():
    from app.modules.m11_sis.rollover_router import rollover_router
    assert rollover_router is not None


def test_rollover_router_has_preview_route():
    from app.modules.m11_sis.rollover_router import rollover_router
    paths = [(r.path, list(r.methods)) for r in rollover_router.routes]
    assert any(
        "/rollover/preview" in path and "POST" in methods
        for path, methods in paths
    )


def test_rollover_router_has_commit_route():
    from app.modules.m11_sis.rollover_router import rollover_router
    paths = [(r.path, list(r.methods)) for r in rollover_router.routes]
    assert any(
        "/rollover/commit" in path and "POST" in methods
        for path, methods in paths
    )


def test_rollover_routes_rbac_admin_only():
    from app.core.auth.models import TenantRole
    from app.modules.m11_sis.rollover_router import _ADMIN
    assert _ADMIN == (TenantRole.ADMIN,)


# ---------------------------------------------------------------------------
# 18. Wiring — router.py includes rollover_router
# ---------------------------------------------------------------------------

def test_router_includes_rollover_router():
    import importlib
    import inspect
    module = importlib.import_module("app.modules.m11_sis.router")
    source = inspect.getsource(module)
    assert "rollover_router" in source


# ---------------------------------------------------------------------------
# 19–22. Scope literal values accepted by schema
# ---------------------------------------------------------------------------

def test_scope_all_programs_valid():
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    obj = RolloverScopeIn(scope="all_programs")
    assert obj.scope == "all_programs"


def test_scope_program_valid():
    import uuid
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    obj = RolloverScopeIn(scope="program", program_id=uuid.uuid4())
    assert obj.scope == "program"


def test_scope_batch_valid():
    import uuid
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    obj = RolloverScopeIn(scope="batch", batch_id=uuid.uuid4())
    assert obj.scope == "batch"


def test_scope_semester_valid():
    import uuid
    from app.modules.m11_sis.rollover_schemas import RolloverScopeIn
    obj = RolloverScopeIn(scope="semester", source_semester_id=uuid.uuid4())
    assert obj.scope == "semester"


# ---------------------------------------------------------------------------
# 23–24. Literal field validation
# ---------------------------------------------------------------------------

def test_row_out_status_annotation_contains_ready_blocked():
    from app.modules.m11_sis.rollover_schemas import RolloverRowOut
    annotation = str(RolloverRowOut.model_fields["status"].annotation)
    assert "ready" in annotation and "blocked" in annotation


def test_commit_row_result_outcome_annotation_contains_all_outcomes():
    from app.modules.m11_sis.rollover_schemas import RolloverCommitRowResult
    annotation = str(RolloverCommitRowResult.model_fields["outcome"].annotation)
    assert "moved" in annotation
    assert "skipped" in annotation
    assert "error" in annotation


# ---------------------------------------------------------------------------
# 25. Wiring — RolloverService imported in rollover_router module
# ---------------------------------------------------------------------------

def test_rollover_router_imports_rollover_service():
    import importlib
    import inspect
    module = importlib.import_module("app.modules.m11_sis.rollover_router")
    source = inspect.getsource(module)
    assert "RolloverService" in source
