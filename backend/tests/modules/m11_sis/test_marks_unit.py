"""
Unit tests — H57 SIS Internal Marks Management

No live database. All tests use import + assert + inspect source.

Coverage groups:
  1–5    Schema field presence
  6–10   Component templates
  11–15  Component create/list/get/update/delete logic stubs
  16–20  Lifecycle: DRAFT→PUBLISHED, PUBLISHED→LOCKED, LOCKED→PUBLISHED
  21–25  Invalid lifecycle transitions
  26–30  Faculty RBAC enforcement (source inspection)
  31–35  Marks entry: bulk UPSERT, first vs edit
  36–40  Marks entry: edit_reason enforcement
  41–43  Marks blocked on LOCKED component
  44–46  Student self-view: DRAFT hidden at SQL level
  47–49  Excel import/export stubs
  50–52  Readiness indicators
  53–56  Audit events registered
  57–59  Notification type registered
  60–62  Router route count
"""
import inspect

import pytest


# ---------------------------------------------------------------------------
# 1. ComponentOut fields
# ---------------------------------------------------------------------------

def test_component_out_required_fields():
    from app.modules.m11_sis.marks_schemas import ComponentOut
    fields = set(ComponentOut.model_fields)
    assert {"id", "course_id", "section_id", "semester_id", "created_by",
            "component_type", "name", "max_marks", "status",
            "is_active", "entries_count", "filled_count", "created_at"} <= fields


def test_component_out_optional_lifecycle_fields():
    from app.modules.m11_sis.marks_schemas import ComponentOut
    fields = set(ComponentOut.model_fields)
    assert {"published_at", "locked_at", "locked_by",
            "reopened_by", "reopened_at", "reopen_reason"} <= fields


# ---------------------------------------------------------------------------
# 2. MarkEntryOut fields
# ---------------------------------------------------------------------------

def test_mark_entry_out_required_fields():
    from app.modules.m11_sis.marks_schemas import MarkEntryOut
    fields = set(MarkEntryOut.model_fields)
    assert {"id", "component_id", "student_id", "marks_obtained",
            "marked_by", "marked_at", "edited_by", "edited_at", "edit_reason",
            "created_at"} <= fields


def test_mark_entry_out_enriched_fields():
    from app.modules.m11_sis.marks_schemas import MarkEntryOut
    fields = set(MarkEntryOut.model_fields)
    assert {"student_name", "usn"} <= fields


# ---------------------------------------------------------------------------
# 3. BulkMarkEntryIn / SingleMarkEditIn
# ---------------------------------------------------------------------------

def test_bulk_mark_entry_in_fields():
    from app.modules.m11_sis.marks_schemas import BulkMarkEntryIn, MarkEntryItem
    assert {"entries", "edit_reason"} <= set(BulkMarkEntryIn.model_fields)
    assert {"student_id", "marks_obtained", "remarks"} <= set(MarkEntryItem.model_fields)


def test_single_mark_edit_has_edit_reason():
    from app.modules.m11_sis.marks_schemas import SingleMarkEditIn
    assert "edit_reason" in SingleMarkEditIn.model_fields


# ---------------------------------------------------------------------------
# 4. Excel import schemas
# ---------------------------------------------------------------------------

def test_marks_import_preview_out_fields():
    from app.modules.m11_sis.marks_schemas import MarksImportPreviewOut
    fields = set(MarksImportPreviewOut.model_fields)
    assert {"component_id", "component_name", "max_marks",
            "total_rows", "valid_rows", "invalid_rows", "rows"} <= fields


def test_marks_import_row_result_fields():
    from app.modules.m11_sis.marks_schemas import MarksImportRowResult
    fields = set(MarksImportRowResult.model_fields)
    assert {"row_number", "is_valid", "errors", "student_id",
            "student_name", "usn", "marks_obtained"} <= fields


def test_marks_import_commit_result_fields():
    from app.modules.m11_sis.marks_schemas import MarksImportCommitResult
    fields = set(MarksImportCommitResult.model_fields)
    assert {"component_id", "total", "saved", "skipped", "errors"} <= fields


# ---------------------------------------------------------------------------
# 5. Student self-view schemas
# ---------------------------------------------------------------------------

def test_student_course_marks_has_total_fields():
    from app.modules.m11_sis.marks_schemas import StudentCourseMarks
    fields = set(StudentCourseMarks.model_fields)
    assert {"total_marks_obtained", "total_max_marks"} <= fields


def test_my_marks_out_fields():
    from app.modules.m11_sis.marks_schemas import MyMarksOut
    fields = set(MyMarksOut.model_fields)
    assert {"student_id", "student_name", "usn", "courses"} <= fields


# ---------------------------------------------------------------------------
# 6–10. Component templates
# ---------------------------------------------------------------------------

def test_built_in_templates_count():
    from app.modules.m11_sis.marks_schemas import BUILT_IN_TEMPLATES
    assert len(BUILT_IN_TEMPLATES) == 5


def test_built_in_templates_keys():
    from app.modules.m11_sis.marks_schemas import BUILT_IN_TEMPLATES
    keys = {t.template_key for t in BUILT_IN_TEMPLATES}
    assert {"CIE_1", "CIE_2", "ASSIGNMENT", "QUIZ", "LAB"} == keys


def test_built_in_templates_names():
    from app.modules.m11_sis.marks_schemas import BUILT_IN_TEMPLATES
    names = {t.name for t in BUILT_IN_TEMPLATES}
    assert {"CIE-1", "CIE-2", "Assignment", "Quiz", "Lab"} == names


def test_built_in_templates_types():
    from app.modules.m11_sis.marks_schemas import BUILT_IN_TEMPLATES
    types = {t.component_type for t in BUILT_IN_TEMPLATES}
    assert {"CIE", "ASSIGNMENT", "QUIZ", "LAB"} <= types


def test_component_template_schema_fields():
    from app.modules.m11_sis.marks_schemas import ComponentTemplate
    fields = set(ComponentTemplate.model_fields)
    assert {"template_key", "component_type", "name", "max_marks", "display_order"} <= fields


# ---------------------------------------------------------------------------
# 11–15. Models — ORM class and field presence
# ---------------------------------------------------------------------------

def test_sis_marks_component_orm_tablename():
    from app.modules.m11_sis.marks_models import SisMarksComponent
    assert SisMarksComponent.__tablename__ == "sis_marks_components"


def test_sis_marks_entry_orm_tablename():
    from app.modules.m11_sis.marks_models import SisMarksEntry
    assert SisMarksEntry.__tablename__ == "sis_marks_entries"


def test_sis_marks_component_columns():
    from app.modules.m11_sis.marks_models import SisMarksComponent
    cols = {c.name for c in SisMarksComponent.__table__.columns}
    assert {"id", "course_id", "section_id", "semester_id", "created_by",
            "component_type", "name", "max_marks", "status",
            "published_at", "locked_at", "locked_by",
            "reopened_by", "reopened_at", "reopen_reason",
            "is_active", "created_at", "updated_at"} <= cols


def test_sis_marks_entry_columns():
    from app.modules.m11_sis.marks_models import SisMarksEntry
    cols = {c.name for c in SisMarksEntry.__table__.columns}
    assert {"id", "component_id", "student_id", "marks_obtained",
            "marked_by", "marked_at", "edited_by", "edited_at", "edit_reason",
            "created_at", "updated_at"} <= cols


def test_component_status_enum_values():
    from app.modules.m11_sis.marks_models import ComponentStatus
    assert set(ComponentStatus) == {ComponentStatus.DRAFT, ComponentStatus.PUBLISHED, ComponentStatus.LOCKED}


# ---------------------------------------------------------------------------
# 16–20. Lifecycle state machine — source inspection
# ---------------------------------------------------------------------------

def test_publish_checks_draft_status():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.publish_component)
    assert "NOT_DRAFT" in src
    assert "DRAFT" in src


def test_lock_checks_published_status():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.lock_component)
    assert "NOT_PUBLISHED" in src
    assert "PUBLISHED" in src


def test_reopen_checks_locked_status():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.reopen_component)
    assert "NOT_LOCKED" in src
    assert "LOCKED" in src


def test_reopen_records_reopened_by_at_reason():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.reopen_component)
    assert "reopened_by" in src
    assert "reopened_at" in src
    assert "reopen_reason" in src


def test_reopen_audits_with_reopened_event():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.reopen_component)
    assert "INTERNAL_MARKS_COMPONENT_REOPENED" in src


# ---------------------------------------------------------------------------
# 21–25. Invalid lifecycle transitions
# ---------------------------------------------------------------------------

def test_update_component_rejects_non_draft():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.update_component)
    assert "NOT_DRAFT" in src


def test_delete_component_rejects_non_draft():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.delete_component)
    assert "NOT_DRAFT" in src


def test_bulk_enter_rejects_locked():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.bulk_enter_marks)
    assert "MARKS_LOCKED" in src


def test_edit_entry_rejects_locked():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.edit_single_entry)
    assert "MARKS_LOCKED" in src


def test_lock_reopen_records_actor():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.lock_component)
    assert "locked_by" in src


# ---------------------------------------------------------------------------
# 26–30. Faculty RBAC enforcement
# ---------------------------------------------------------------------------

def test_create_component_verifies_assignment():
    # Component creation resolves its class first; that resolution is what
    # verifies the faculty actually teaches the course (in the section for a
    # regular course, in the term for an elective group).
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.create_component)
    assert "_resolve_component_class" in src


def test_resolve_component_class_verifies_faculty_on_both_paths():
    from app.modules.m11_sis.marks_service import _resolve_component_class
    src = inspect.getsource(_resolve_component_class)
    # Elective: the class is the term, so the check is (course, semester).
    assert "is_elective_course" in src
    assert "_assert_faculty_teaches" in src
    # Regular course: the class is the section, and the section still gates it.
    assert "_verify_faculty_assignment" in src


def test_elective_component_rejects_a_section():
    # An elective is taught to one combined class, never to a section. Passing a
    # section would silently halve the roster, so the semester is required.
    from app.modules.m11_sis.marks_service import _resolve_component_class
    src = inspect.getsource(_resolve_component_class)
    assert "SEMESTER_REQUIRED" in src
    assert "return None, body.semester_id" in src


def test_publish_component_checks_faculty_ownership():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.publish_component)
    assert "created_by" in src and "FORBIDDEN" in src


def test_bulk_enter_checks_faculty_ownership():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.bulk_enter_marks)
    assert "created_by" in src and "FORBIDDEN" in src


def test_verify_faculty_uses_subject_assignments():
    # The subject_assignments lookup lives in _assert_faculty_teaches, keyed on
    # (course, semester) so one faculty can own an elective spanning sections.
    from app.modules.m11_sis.marks_service import _assert_faculty_teaches
    src = inspect.getsource(_assert_faculty_teaches)
    assert "SubjectAssignment" in src
    assert "PRIMARY" in src
    assert "CO_FACULTY" in src
    assert "semester_id" in src


def test_verify_faculty_raises_not_assigned():
    from app.modules.m11_sis.marks_service import _assert_faculty_teaches
    src = inspect.getsource(_assert_faculty_teaches)
    assert "NOT_ASSIGNED" in src


def test_section_path_still_gates_on_the_section():
    # A regular course must still resolve and validate its section before the
    # assignment check — dropping that would let faculty mark any section.
    from app.modules.m11_sis.marks_service import _verify_faculty_assignment
    src = inspect.getsource(_verify_faculty_assignment)
    assert "SECTION_NOT_FOUND" in src
    assert "SECTION_INACTIVE" in src
    assert "_assert_faculty_teaches" in src


# ---------------------------------------------------------------------------
# 31–35. Bulk UPSERT logic
# ---------------------------------------------------------------------------

def test_bulk_upsert_method_exists():
    from app.modules.m11_sis.marks_repository import MarksRepository
    assert hasattr(MarksRepository, "bulk_upsert_entries")
    assert callable(MarksRepository.bulk_upsert_entries)


def test_bulk_upsert_returns_tuple():
    src = inspect.getsource(__import__(
        "app.modules.m11_sis.marks_repository", fromlist=["MarksRepository"]
    ).MarksRepository.bulk_upsert_entries)
    assert "first_marks" in src
    assert "edits" in src


def test_bulk_upsert_sets_marked_by_on_first():
    from app.modules.m11_sis.marks_repository import MarksRepository
    src = inspect.getsource(MarksRepository.bulk_upsert_entries)
    assert "marked_by" in src


def test_bulk_upsert_sets_edited_by_on_repeat():
    from app.modules.m11_sis.marks_repository import MarksRepository
    src = inspect.getsource(MarksRepository.bulk_upsert_entries)
    assert "edited_by" in src and "edit_reason" in src


def test_marks_exceeded_rejected():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.bulk_enter_marks)
    assert "MARKS_EXCEEDED" in src
    assert "max_marks" in src


# ---------------------------------------------------------------------------
# 36–40. Edit reason enforcement
# ---------------------------------------------------------------------------

def test_bulk_enter_requires_reason_on_published():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.bulk_enter_marks)
    assert "EDIT_REASON_REQUIRED" in src
    assert "PUBLISHED" in src


def test_single_edit_requires_reason_on_published():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.edit_single_entry)
    assert "EDIT_REASON_REQUIRED" in src
    assert "PUBLISHED" in src


def test_import_commit_requires_reason_on_published():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.import_commit)
    assert "EDIT_REASON_REQUIRED" in src


def test_reopen_component_requires_reason_field():
    from app.modules.m11_sis.marks_schemas import ReopenComponentIn
    f = ReopenComponentIn.model_fields["reason"]
    assert f.metadata  # has min_length validator


def test_edit_reason_stored_on_entry():
    from app.modules.m11_sis.marks_repository import MarksRepository
    src = inspect.getsource(MarksRepository.bulk_upsert_entries)
    assert "edit_reason" in src


# ---------------------------------------------------------------------------
# 41–43. LOCKED guard
# ---------------------------------------------------------------------------

def test_import_preview_rejects_locked():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.import_preview)
    assert "MARKS_LOCKED" in src


def test_bulk_enter_locked_check_precedes_upsert():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.bulk_enter_marks)
    locked_pos = src.index("MARKS_LOCKED")
    upsert_pos = src.index("bulk_upsert_entries")
    assert locked_pos < upsert_pos


def test_edit_entry_locked_check_precedes_update():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.edit_single_entry)
    locked_pos = src.index("MARKS_LOCKED")
    update_pos = src.index("update_entry")
    assert locked_pos < update_pos


# ---------------------------------------------------------------------------
# 44–46. Student self-view — DRAFT hidden at SQL level
# ---------------------------------------------------------------------------

def test_student_marks_sql_filters_published_locked():
    from app.modules.m11_sis.marks_repository import MarksRepository
    src = inspect.getsource(MarksRepository.get_student_marks_raw)
    assert "PUBLISHED" in src and "LOCKED" in src
    assert "DRAFT" not in src


def test_my_marks_out_groups_by_course():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.get_my_marks)
    assert "course_map" in src


def test_student_course_marks_totals_computed():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.get_my_marks)
    assert "total_marks_obtained" in src
    assert "total_max_marks" in src


# ---------------------------------------------------------------------------
# 47–49. Excel import/export
# ---------------------------------------------------------------------------

def test_get_excel_template_exists():
    from app.modules.m11_sis.marks_service import MarksService
    assert callable(MarksService.get_excel_template)


def test_import_preview_delegates_parsing():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.import_preview)
    assert "OnboardingService._parse_file" in src


def test_import_commit_re_validates():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.import_commit)
    assert "import_preview" in src


# ---------------------------------------------------------------------------
# 50–52. Readiness indicators
# ---------------------------------------------------------------------------

def test_readiness_schema_fields():
    from app.modules.m11_sis.marks_schemas import StudentReadiness, SectionReadinessOut
    sr = set(StudentReadiness.model_fields)
    assert {"attendance_ready", "internal_marks_ready",
            "attendance_pct", "marks_fill_pct", "notes"} <= sr
    out = set(SectionReadinessOut.model_fields)
    assert {"attendance_ready_count", "internal_marks_ready_count", "fully_ready_count", "students"} <= out


def test_readiness_advisory_only():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService.get_section_readiness)
    assert "notes" in src
    # No autonomous rejection
    assert "reject" not in src.lower()
    assert "block" not in src.lower()


def test_readiness_uses_locked_attendance_sessions():
    from app.modules.m11_sis.marks_repository import MarksRepository
    src = inspect.getsource(MarksRepository.get_section_readiness_raw)
    assert "status = 'LOCKED'" in src or "status='LOCKED'" in src


# ---------------------------------------------------------------------------
# 53–56. Audit events registered
# ---------------------------------------------------------------------------

def test_audit_component_created_event():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "INTERNAL_MARKS_COMPONENT_CREATED")


def test_audit_component_updated_event():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "INTERNAL_MARKS_COMPONENT_UPDATED")


def test_audit_component_reopened_event():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "INTERNAL_MARKS_COMPONENT_REOPENED")


def test_audit_marks_entered_and_edited_events():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "INTERNAL_MARKS_ENTERED")
    assert hasattr(AuditEventType, "INTERNAL_MARKS_EDITED")


# ---------------------------------------------------------------------------
# 57–59. Notification type registered
# ---------------------------------------------------------------------------

def test_notification_marks_published_type():
    from app.core.notifications.models import NotificationType
    assert hasattr(NotificationType, "INTERNAL_MARKS_PUBLISHED")


def test_publish_triggers_student_notification():
    from app.modules.m11_sis.marks_service import MarksService
    src = inspect.getsource(MarksService._notify_students_on_publish)
    assert "INTERNAL_MARKS_PUBLISHED" in src


def test_notify_safe_is_fire_and_forget():
    from app.modules.m11_sis.marks_service import _notify_safe
    src = inspect.getsource(_notify_safe)
    assert "except Exception" in src   # swallowed; never crashes caller


# ---------------------------------------------------------------------------
# 60–62. Router routes registered
# ---------------------------------------------------------------------------

def test_marks_router_has_template_route():
    from app.modules.m11_sis.marks_router import marks_router
    paths = {r.path for r in marks_router.routes}
    assert "/marks/component-templates" in paths


def test_marks_router_has_lifecycle_routes():
    from app.modules.m11_sis.marks_router import marks_router
    paths = {r.path for r in marks_router.routes}
    assert "/marks/components/{component_id}/publish" in paths
    assert "/marks/components/{component_id}/lock"    in paths
    assert "/marks/components/{component_id}/reopen"  in paths


def test_sis_router_total_route_count():
    from app.modules.m11_sis.router import router
    from app.modules.m11_sis.marks_router import marks_router
    # M11 base routes (schools) = 5
    # sub-routers merged: count marks_router explicitly
    marks_routes = len(marks_router.routes)
    assert marks_routes >= 17   # 17 new marks routes
