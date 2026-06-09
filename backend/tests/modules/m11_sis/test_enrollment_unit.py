"""
Unit tests — M11-002 SIS Student Enrollment Center

No live database.  All tests use import + assert.

Coverage:
  1. Schemas: field presence, model_config
  2. Repository: method signatures present
  3. EnrollmentServiceError: code / message / status_code
  4. EnrollmentService: all static methods present
  5. Router: all 7 enrollment routes registered; correct HTTP methods
  6. RBAC: _WRITE=ADMIN only; _READ=ADMIN+DEAN
  7. Audit events: ENROLLMENT_* present in AuditEventType
  8. Business rules documented in service source
"""
import inspect
import pytest


# ---------------------------------------------------------------------------
# 1. Schemas
# ---------------------------------------------------------------------------

def test_enroll_student_in_fields():
    from app.modules.m11_sis.enrollment_schemas import EnrollStudentIn
    fields = set(EnrollStudentIn.model_fields)
    assert {"student_id", "section_id"} <= fields


def test_move_student_in_field():
    from app.modules.m11_sis.enrollment_schemas import MoveStudentIn
    assert "target_section_id" in MoveStudentIn.model_fields


def test_enrollment_out_from_attributes():
    from app.modules.m11_sis.enrollment_schemas import EnrollmentOut
    assert EnrollmentOut.model_config.get("from_attributes") is True


def test_enrollment_out_fields():
    from app.modules.m11_sis.enrollment_schemas import EnrollmentOut
    assert {"id", "student_id", "section_id", "enrolled_at", "is_active"} <= set(EnrollmentOut.model_fields)


def test_roster_student_out_fields():
    from app.modules.m11_sis.enrollment_schemas import RosterStudentOut
    expected = {"enrollment_id", "student_id", "full_name", "email", "identifier", "enrolled_at", "is_active"}
    assert expected <= set(RosterStudentOut.model_fields)


def test_student_summary_out_has_is_enrolled():
    from app.modules.m11_sis.enrollment_schemas import StudentSummaryOut
    assert "is_enrolled" in StudentSummaryOut.model_fields


def test_student_profile_out_fields():
    from app.modules.m11_sis.enrollment_schemas import StudentProfileOut
    expected = {"student_id", "full_name", "email", "identifier", "program", "department", "batch", "enrollment"}
    assert expected <= set(StudentProfileOut.model_fields)


def test_dashboard_counts_out_fields():
    from app.modules.m11_sis.enrollment_schemas import DashboardCountsOut
    expected = {"schools", "departments", "programs", "active_batches", "semesters", "sections", "enrolled_students"}
    assert expected <= set(DashboardCountsOut.model_fields)


# ---------------------------------------------------------------------------
# 2. Repository methods
# ---------------------------------------------------------------------------

def test_enrollment_repository_methods():
    from app.modules.m11_sis.enrollment_repository import EnrollmentRepository
    for m in ("get_roster", "get_by_id", "get_by_student",
              "create", "reenroll", "unenroll", "move",
              "list_students", "get_student_profile", "get_dashboard_counts"):
        assert callable(getattr(EnrollmentRepository, m, None)), f"EnrollmentRepository.{m} missing"


# ---------------------------------------------------------------------------
# 3. EnrollmentServiceError
# ---------------------------------------------------------------------------

def test_enrollment_service_error_attrs():
    from app.modules.m11_sis.enrollment_service import EnrollmentServiceError
    e = EnrollmentServiceError("ALREADY_ENROLLED", "Already enrolled.", 409)
    assert e.code == "ALREADY_ENROLLED"
    assert e.message == "Already enrolled."
    assert e.status_code == 409


def test_enrollment_service_error_default_status():
    from app.modules.m11_sis.enrollment_service import EnrollmentServiceError
    e = EnrollmentServiceError("OOPS", "Something went wrong")
    assert e.status_code == 400


# ---------------------------------------------------------------------------
# 4. EnrollmentService methods
# ---------------------------------------------------------------------------

def test_enrollment_service_methods():
    from app.modules.m11_sis.enrollment_service import EnrollmentService
    for m in ("get_roster", "enroll_student", "unenroll", "move_student",
              "list_students", "get_student_profile", "get_dashboard_counts"):
        assert callable(getattr(EnrollmentService, m, None)), f"EnrollmentService.{m} missing"


# ---------------------------------------------------------------------------
# 5. Router — all 7 enrollment routes registered with correct methods
# ---------------------------------------------------------------------------

def _enrollment_routes():
    from app.modules.m11_sis.enrollment_router import enrollment_router
    return {r.path: {m for m in getattr(r, "methods", set())} for r in enrollment_router.routes}


def test_enrollment_router_route_count():
    from app.modules.m11_sis.enrollment_router import enrollment_router
    assert len(enrollment_router.routes) == 7


def test_enrollment_router_dashboard_counts():
    routes = _enrollment_routes()
    assert "GET" in routes.get("/dashboard/counts", set())


def test_enrollment_router_roster():
    routes = _enrollment_routes()
    assert "GET" in routes.get("/sections/{section_id}/roster", set())


def test_enrollment_router_students_list():
    routes = _enrollment_routes()
    assert "GET" in routes.get("/students", set())


def test_enrollment_router_student_profile():
    routes = _enrollment_routes()
    assert "GET" in routes.get("/students/{student_id}/profile", set())


def test_enrollment_router_enroll_post():
    routes = _enrollment_routes()
    assert "POST" in routes.get("/enrollments", set())


def test_enrollment_router_unenroll_delete():
    routes = _enrollment_routes()
    assert "DELETE" in routes.get("/enrollments/{enrollment_id}", set())


def test_enrollment_router_move_post():
    routes = _enrollment_routes()
    assert "POST" in routes.get("/enrollments/{enrollment_id}/move", set())


# ---------------------------------------------------------------------------
# 6. RBAC
# ---------------------------------------------------------------------------

def test_rbac_write_is_admin_only():
    from app.modules.m11_sis.enrollment_router import _WRITE
    from app.core.auth.models import TenantRole
    assert TenantRole.ADMIN in _WRITE
    assert TenantRole.DEAN not in _WRITE
    assert TenantRole.FACULTY not in _WRITE
    assert TenantRole.STUDENT not in _WRITE


def test_rbac_read_includes_admin_and_dean():
    from app.modules.m11_sis.enrollment_router import _READ
    from app.core.auth.models import TenantRole
    assert TenantRole.ADMIN in _READ
    assert TenantRole.DEAN in _READ
    assert TenantRole.FACULTY not in _READ
    assert TenantRole.STUDENT not in _READ


# ---------------------------------------------------------------------------
# 7. Audit events
# ---------------------------------------------------------------------------

def test_enrollment_audit_events_present():
    from app.core.audit_log.models import AuditEventType
    values = {e.value for e in AuditEventType}
    assert "ENROLLMENT_CREATED"    in values
    assert "ENROLLMENT_UNENROLLED" in values
    assert "ENROLLMENT_MOVED"      in values


def test_prior_sis_audit_events_not_regressed():
    from app.core.audit_log.models import AuditEventType
    values = {e.value for e in AuditEventType}
    for expected in ("SCHOOL_CREATED", "SCHOOL_UPDATED", "SCHOOL_DELETED"):
        assert expected in values, f"{expected} regressed"


# ---------------------------------------------------------------------------
# 8. Business rules in service source
# ---------------------------------------------------------------------------

def test_service_handles_reenroll():
    src = inspect.getsource(__import__("app.modules.m11_sis.enrollment_service", fromlist=["enrollment_service"]))
    assert "reenroll" in src
    assert "ALREADY_ENROLLED" in src


def test_service_validates_student_role():
    src = inspect.getsource(__import__("app.modules.m11_sis.enrollment_service", fromlist=["enrollment_service"]))
    assert "NOT_A_STUDENT" in src
    assert "TenantRole.STUDENT" in src


def test_service_move_validates_same_section():
    src = inspect.getsource(__import__("app.modules.m11_sis.enrollment_service", fromlist=["enrollment_service"]))
    assert "SAME_SECTION" in src


# ---------------------------------------------------------------------------
# 9. Main sis router includes enrollment routes
# ---------------------------------------------------------------------------

def test_sis_router_includes_enrollment_routes():
    from app.modules.m11_sis.router import router
    paths = [r.path for r in router.routes]
    assert "/enrollments" in paths
    assert "/dashboard/counts" in paths
    assert "/students" in paths
    assert "/sections/{section_id}/roster" in paths


def test_sis_router_total_routes():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover + 15 attendance
    # + 19 marks + 10 hallticket + 24 exam + 36 results = 133
    assert len(router.routes) == 173
