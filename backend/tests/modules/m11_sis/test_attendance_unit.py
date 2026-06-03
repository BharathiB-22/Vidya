"""
Unit tests — H55 SIS Attendance Management

No live database.  All tests use import + assert only.

Coverage:
  1–9:   Models and enums
  10–22: Schemas (field presence, validators)
  23–32: Repository (method presence)
  33–40: Service (method presence, helpers)
  41–52: Router (routes registered, RBAC constants)
  53–55: Audit and notification wiring
"""
import inspect
import pytest


# ---------------------------------------------------------------------------
# 1–9. Models & Enums
# ---------------------------------------------------------------------------

def test_session_status_enum_values():
    from app.modules.m11_sis.attendance_models import SessionStatus
    assert SessionStatus.OPEN   == "OPEN"
    assert SessionStatus.LOCKED == "LOCKED"


def test_attendance_status_enum_values():
    from app.modules.m11_sis.attendance_models import AttendanceStatus
    assert AttendanceStatus.PRESENT == "PRESENT"
    assert AttendanceStatus.ABSENT  == "ABSENT"
    assert AttendanceStatus.LATE    == "LATE"
    assert AttendanceStatus.EXCUSED == "EXCUSED"


def test_session_model_importable():
    from app.modules.m11_sis.attendance_models import SisAttendanceSession
    assert SisAttendanceSession.__tablename__ == "sis_attendance_sessions"


def test_session_model_context_columns():
    from app.modules.m11_sis.attendance_models import SisAttendanceSession
    cols = {c.name for c in SisAttendanceSession.__table__.columns}
    assert {"id", "course_id", "section_id", "faculty_user_id"} <= cols


def test_session_model_when_columns():
    from app.modules.m11_sis.attendance_models import SisAttendanceSession
    cols = {c.name for c in SisAttendanceSession.__table__.columns}
    assert {"session_date", "period_number", "duration_minutes"} <= cols


def test_session_model_lifecycle_columns():
    from app.modules.m11_sis.attendance_models import SisAttendanceSession
    cols = {c.name for c in SisAttendanceSession.__table__.columns}
    assert {"status", "first_marked_at", "locked_at"} <= cols


def test_session_model_reopen_columns():
    from app.modules.m11_sis.attendance_models import SisAttendanceSession
    cols = {c.name for c in SisAttendanceSession.__table__.columns}
    assert {"reopened_by", "reopened_at", "reopen_reason"} <= cols


def test_record_model_importable():
    from app.modules.m11_sis.attendance_models import SisAttendanceRecord
    assert SisAttendanceRecord.__tablename__ == "sis_attendance_records"


def test_record_model_all_columns():
    from app.modules.m11_sis.attendance_models import SisAttendanceRecord
    cols = {c.name for c in SisAttendanceRecord.__table__.columns}
    assert {"id", "session_id", "student_id", "status", "remarks",
            "marked_by", "marked_at", "edited_by", "edited_at", "edit_reason"} <= cols


def test_record_unique_constraint():
    from app.modules.m11_sis.attendance_models import SisAttendanceRecord
    constraints = {c.name for c in SisAttendanceRecord.__table__.constraints}
    assert "uq_att_records_session_student" in constraints


# ---------------------------------------------------------------------------
# 10–22. Schemas
# ---------------------------------------------------------------------------

def test_session_create_in_required_fields():
    from app.modules.m11_sis.attendance_schemas import SessionCreateIn
    assert {"course_id", "section_id", "session_date"} <= set(SessionCreateIn.model_fields)


def test_session_create_in_optional_fields():
    from app.modules.m11_sis.attendance_schemas import SessionCreateIn
    assert {"period_number", "duration_minutes", "topic_covered"} <= set(SessionCreateIn.model_fields)
    # Optional fields should default to None
    obj = SessionCreateIn(
        course_id="00000000-0000-0000-0000-000000000001",
        section_id="00000000-0000-0000-0000-000000000002",
        session_date="2026-06-10",
    )
    assert obj.period_number is None


def test_attendance_mark_entry_fields():
    from app.modules.m11_sis.attendance_schemas import AttendanceMarkEntry
    assert {"student_id", "status", "remarks"} <= set(AttendanceMarkEntry.model_fields)


def test_attendance_mark_in_has_edit_reason():
    from app.modules.m11_sis.attendance_schemas import AttendanceMarkIn
    assert "edit_reason" in AttendanceMarkIn.model_fields
    assert "records" in AttendanceMarkIn.model_fields


def test_record_edit_in_has_edit_reason():
    from app.modules.m11_sis.attendance_schemas import RecordEditIn
    assert "edit_reason" in RecordEditIn.model_fields


def test_reopen_session_in_requires_reason():
    from pydantic import ValidationError
    from app.modules.m11_sis.attendance_schemas import ReopenSessionIn
    with pytest.raises(ValidationError):
        ReopenSessionIn(reason="")  # empty string should fail


def test_session_out_computed_fields():
    from app.modules.m11_sis.attendance_schemas import SessionOut
    fields = set(SessionOut.model_fields)
    assert {"is_editable", "minutes_until_lock", "first_marked_at"} <= fields


def test_session_out_attendance_counts():
    from app.modules.m11_sis.attendance_schemas import SessionOut
    fields = set(SessionOut.model_fields)
    assert {"present_count", "absent_count", "late_count", "excused_count",
            "attendance_pct", "total_enrolled"} <= fields


def test_record_out_audit_fields():
    from app.modules.m11_sis.attendance_schemas import AttendanceRecordOut
    fields = set(AttendanceRecordOut.model_fields)
    assert {"marked_by", "marked_at", "edited_by", "edited_at", "edit_reason"} <= fields


def test_course_attendance_summary_formula_fields():
    from app.modules.m11_sis.attendance_schemas import CourseAttendanceSummary
    fields = set(CourseAttendanceSummary.model_fields)
    assert {"attended_sessions", "excused_sessions", "total_countable",
            "attendance_pct", "is_at_risk"} <= fields


def test_shortage_report_out_fields():
    from app.modules.m11_sis.attendance_schemas import ShortageReportOut
    assert {"threshold_pct", "total_at_risk", "students"} <= set(ShortageReportOut.model_fields)


def test_dashboard_out_fields():
    from app.modules.m11_sis.attendance_schemas import AttendanceDashboardOut
    expected = {"today_sessions", "marked_today", "pending_sessions",
                "students_below_threshold", "threshold_pct"}
    assert expected <= set(AttendanceDashboardOut.model_fields)


def test_my_attendance_summary_fields():
    from app.modules.m11_sis.attendance_schemas import MyAttendanceSummary
    assert {"student_id", "overall_pct", "courses"} <= set(MyAttendanceSummary.model_fields)


# ---------------------------------------------------------------------------
# 23–32. Repository methods
# ---------------------------------------------------------------------------

def test_repository_importable():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    assert AttendanceRepository is not None


def test_repository_session_methods():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    for m in ("get_session_by_id", "create_session", "update_session"):
        assert callable(getattr(AttendanceRepository, m, None)), f"AttendanceRepository.{m} missing"


def test_repository_enrollment_method():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    assert callable(getattr(AttendanceRepository, "get_enrolled_student_ids", None))


def test_repository_record_methods():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    for m in ("bulk_create_absent_records", "load_records_map",
              "bulk_mark_records", "get_record_by_id", "edit_record",
              "get_records_by_session"):
        assert callable(getattr(AttendanceRepository, m, None)), f"AttendanceRepository.{m} missing"


def test_repository_list_sessions():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    assert callable(getattr(AttendanceRepository, "list_sessions_enriched", None))


def test_repository_analytics_methods():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    for m in ("get_student_summary_raw", "get_section_analytics_raw",
              "get_shortage_raw", "get_dashboard_raw"):
        assert callable(getattr(AttendanceRepository, m, None)), f"AttendanceRepository.{m} missing"


def test_repository_notification_check():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    assert callable(getattr(AttendanceRepository, "check_shortage_warning_exists", None))


def test_repository_threshold_batch():
    from app.modules.m11_sis.attendance_repository import AttendanceRepository
    assert callable(getattr(AttendanceRepository, "get_students_course_pct_batch", None))


def test_default_shortage_threshold_is_75():
    from app.modules.m11_sis.attendance_repository import DEFAULT_SHORTAGE_THRESHOLD
    assert DEFAULT_SHORTAGE_THRESHOLD == 75.0


# ---------------------------------------------------------------------------
# 33–40. Service
# ---------------------------------------------------------------------------

def test_service_importable():
    from app.modules.m11_sis.attendance_service import AttendanceService
    assert AttendanceService is not None


def test_is_editable_helper_importable():
    from app.modules.m11_sis.attendance_service import is_editable
    assert callable(is_editable)


def test_minutes_until_lock_helper_importable():
    from app.modules.m11_sis.attendance_service import minutes_until_lock
    assert callable(minutes_until_lock)


def test_service_write_methods_are_async():
    from app.modules.m11_sis.attendance_service import AttendanceService
    for m in ("create_session", "mark_attendance", "edit_record", "reopen_session"):
        method = getattr(AttendanceService, m, None)
        assert inspect.iscoroutinefunction(method), f"AttendanceService.{m} must be async"


def test_service_read_methods_are_async():
    from app.modules.m11_sis.attendance_service import AttendanceService
    for m in ("list_sessions", "get_session", "get_session_records",
              "get_my_attendance", "get_my_course_detail",
              "get_section_analytics", "get_shortage_report", "get_dashboard"):
        method = getattr(AttendanceService, m, None)
        assert inspect.iscoroutinefunction(method), f"AttendanceService.{m} must be async"


def test_edit_window_hours_constant():
    from app.modules.m11_sis.attendance_service import ATTENDANCE_EDIT_WINDOW_HOURS
    assert ATTENDANCE_EDIT_WINDOW_HOURS == 48


def test_is_editable_locked_session():
    from app.modules.m11_sis.attendance_service import is_editable

    class _S:
        status = "LOCKED"
        first_marked_at = None
        reopened_at = None

    assert is_editable(_S()) is False  # type: ignore[arg-type]


def test_is_editable_unmarked_open_session():
    from app.modules.m11_sis.attendance_service import is_editable

    class _S:
        status = "OPEN"
        first_marked_at = None
        reopened_at = None

    assert is_editable(_S()) is True  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 41–52. Router
# ---------------------------------------------------------------------------

def test_attendance_router_importable():
    from app.modules.m11_sis.attendance_router import attendance_router
    assert attendance_router is not None


def test_attendance_router_rbac_constants():
    from app.core.auth.models import TenantRole
    from app.modules.m11_sis.attendance_router import _FACULTY_WRITE, _MANAGERS, _STUDENT
    assert _FACULTY_WRITE == (TenantRole.FACULTY,)
    assert set(_MANAGERS) == {TenantRole.ADMIN, TenantRole.DEAN}
    assert _STUDENT == (TenantRole.STUDENT,)


def _get_routes(router):
    return [(r.path, sorted(r.methods)) for r in router.routes]


def test_route_create_session():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/attendance/sessions" in p and "POST" in m for p, m in routes)


def test_route_list_sessions():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/attendance/sessions" in p and "GET" in m for p, m in routes)


def test_route_mark_attendance():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/mark" in p and "POST" in m for p, m in routes)


def test_route_edit_record():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/records/" in p and "PATCH" in m for p, m in routes)


def test_route_reopen_session():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/reopen" in p and "POST" in m for p, m in routes)


def test_route_dashboard():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("dashboard" in p and "GET" in m for p, m in routes)


def test_route_shortage():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("shortage" in p and "GET" in m for p, m in routes)


def test_route_student_me():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/attendance/me" in p and "GET" in m for p, m in routes)


def test_route_student_me_course():
    from app.modules.m11_sis.attendance_router import attendance_router
    routes = _get_routes(attendance_router)
    assert any("/attendance/me/course/" in p and "GET" in m for p, m in routes)


def test_sis_router_includes_attendance_router():
    import importlib, inspect
    module = importlib.import_module("app.modules.m11_sis.router")
    source = inspect.getsource(module)
    assert "attendance_router" in source


def test_sis_router_total_route_count():
    from app.modules.m11_sis.router import router
    # 5 schools + 7 enrollment + 11 directory + 4 me + 2 rollover + 13 attendance = 42
    assert len(router.routes) == 42


# ---------------------------------------------------------------------------
# 53–55. Audit and notification wiring
# ---------------------------------------------------------------------------

def test_audit_event_types_added():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "ATTENDANCE_SESSION_CREATED")
    assert hasattr(AuditEventType, "ATTENDANCE_MARKED")
    assert hasattr(AuditEventType, "ATTENDANCE_EDITED")
    assert hasattr(AuditEventType, "ATTENDANCE_SESSION_REOPENED")


def test_notification_type_added():
    from app.core.notifications.models import NotificationType
    assert hasattr(NotificationType, "ATTENDANCE_SHORTAGE_WARNING")


def test_attendance_shortage_threshold_is_configurable():
    """Threshold is a float parameter, not hardcoded — verify it can be changed."""
    from app.modules.m11_sis.attendance_repository import DEFAULT_SHORTAGE_THRESHOLD
    # Default is 75 but function signatures accept a float parameter
    from app.modules.m11_sis.attendance_service import AttendanceService
    import inspect
    sig = inspect.signature(AttendanceService.get_shortage_report)
    assert "threshold" in sig.parameters
