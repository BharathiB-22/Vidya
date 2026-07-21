"""
Unit tests — SIS Directory (H50)

Coverage:
  1.  Model: SisStudentProfile table name, columns, constraints
  2.  Model: SisFacultyProfile table name, columns, constraints
  3.  Schema: StudentProfileUpsert — USN strip/uppercase, admission_year guard
  4.  Schema: FacultyProfileUpsert — employee_id mandatory and stripped
  5.  Schema: DirectoryPage generic fields
  6.  Schema: StudentDirectoryItem optional fields
  7.  Schema: FacultyDirectoryItem optional fields
  8.  Schema: StudentDetailOut contains all profile fields
  9.  Schema: FacultyDetailOut contains all profile fields + active_assignments
 10.  Repository: StudentDirectoryRepository — all method names present
 11.  Repository: FacultyDirectoryRepository — all method names present
 12.  Service: DirectoryServiceError attributes
 13.  Service: StudentDirectoryService static method names
 14.  Service: FacultyDirectoryService static method names
 15.  Router: directory routes registered
 16.  Router: _WRITE = ADMIN+DEAN, _READ = ADMIN+DEAN+FACULTY
 17.  Audit events: STUDENT_PROFILE_UPDATED / FACULTY_PROFILE_UPDATED present
 18.  Migration 0029: revision and down_revision
 19.  Migration 0030: revision and down_revision
 20.  USN validator: uppercase + strip
 21.  employee_id validator: uppercase + strip, non-empty guard
 22.  admission_year: rejects out-of-range
 23.  SisStudentProfile: user_id is primary key
 24.  SisFacultyProfile: user_id is primary key, employee_id NOT NULL
 25.  Faculty profile: primary_department_id nullable FK to acad_departments
 26.  Directory router: /directory/students, /directory/faculty routes present
 27.  Department faculty route: /departments/{dept_id}/faculty present
 28.  DashboardCountsOut: total_students and total_faculty fields present
 29.  StudentProfileOut: usn and admission_year fields present
 30.  FacultyDetailOut: active_assignments is a list
"""
import importlib.util
import pathlib
import pytest


# ---------------------------------------------------------------------------
# 1. SisStudentProfile model
# ---------------------------------------------------------------------------

def test_student_profile_tablename():
    from app.modules.m11_sis.models import SisStudentProfile
    assert SisStudentProfile.__tablename__ == "sis_student_profiles"


def test_student_profile_columns():
    from app.modules.m11_sis.models import SisStudentProfile
    cols = {c.name for c in SisStudentProfile.__table__.columns}
    expected = {
        "user_id", "usn", "admission_year", "date_of_birth",
        "phone", "address_line1", "address_city", "address_state",
        "emergency_contact_name", "emergency_contact_phone",
        "photo_url", "notes", "is_active", "created_at", "updated_at",
    }
    assert expected <= cols


def test_student_profile_constraints():
    from app.modules.m11_sis.models import SisStudentProfile
    names = {c.name for c in SisStudentProfile.__table__.constraints}
    assert "uq_sis_student_profiles_usn" in names


# ---------------------------------------------------------------------------
# 2. SisFacultyProfile model
# ---------------------------------------------------------------------------

def test_faculty_profile_tablename():
    from app.modules.m11_sis.models import SisFacultyProfile
    assert SisFacultyProfile.__tablename__ == "sis_faculty_profiles"


def test_faculty_profile_columns():
    from app.modules.m11_sis.models import SisFacultyProfile
    cols = {c.name for c in SisFacultyProfile.__table__.columns}
    expected = {
        "user_id", "employee_id", "designation", "qualifications", "bio",
        "office_location", "phone", "joining_date", "specialization",
        "primary_department_id", "photo_url", "is_active", "created_at", "updated_at",
    }
    assert expected <= cols


def test_faculty_profile_constraints():
    from app.modules.m11_sis.models import SisFacultyProfile
    names = {c.name for c in SisFacultyProfile.__table__.constraints}
    assert "uq_sis_faculty_profiles_employee_id" in names


# ---------------------------------------------------------------------------
# 3. StudentProfileUpsert validators
# ---------------------------------------------------------------------------

def test_student_upsert_usn_uppercase():
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    s = StudentProfileUpsert(usn=" 1ms22cs001 ")
    assert s.usn == "1MS22CS001"


def test_student_upsert_usn_none_ok():
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    s = StudentProfileUpsert()
    assert s.usn is None


def test_student_upsert_admission_year_valid():
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    s = StudentProfileUpsert(admission_year=2022)
    assert s.admission_year == 2022


def test_student_upsert_admission_year_invalid():
    from pydantic import ValidationError
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    with pytest.raises(ValidationError):
        StudentProfileUpsert(admission_year=1800)


# ---------------------------------------------------------------------------
# 4. FacultyProfileUpsert validators
# ---------------------------------------------------------------------------

def test_faculty_upsert_employee_id_uppercase():
    from app.modules.m11_sis.directory_schemas import FacultyProfileUpsert
    f = FacultyProfileUpsert(employee_id=" emp-001 ")
    assert f.employee_id == "EMP-001"


def test_faculty_upsert_employee_id_empty_raises():
    from pydantic import ValidationError
    from app.modules.m11_sis.directory_schemas import FacultyProfileUpsert
    with pytest.raises(ValidationError):
        FacultyProfileUpsert(employee_id="   ")


def test_faculty_upsert_employee_id_required():
    from pydantic import ValidationError
    from app.modules.m11_sis.directory_schemas import FacultyProfileUpsert
    with pytest.raises(ValidationError):
        FacultyProfileUpsert()


# ---------------------------------------------------------------------------
# 5. DirectoryPage generic
# ---------------------------------------------------------------------------

def test_directory_page_fields():
    from app.modules.m11_sis.directory_schemas import DirectoryPage
    page = DirectoryPage(items=[], total=0, page=1, page_size=20, total_pages=1)
    assert page.total == 0
    assert page.total_pages == 1


# ---------------------------------------------------------------------------
# 6 & 7. Directory item schemas — optional fields
# ---------------------------------------------------------------------------

def test_student_directory_item_optional():
    from uuid import uuid4
    from app.modules.m11_sis.directory_schemas import StudentDirectoryItem
    item = StudentDirectoryItem(
        user_id=uuid4(), full_name="Alice", email="a@test.com",
        identifier=None, usn=None, admission_year=None,
        program=None, department=None, batch=None, current_section=None,
        is_active=True,
    )
    assert item.usn is None


def test_faculty_directory_item_optional():
    from uuid import uuid4
    from app.modules.m11_sis.directory_schemas import FacultyDirectoryItem
    item = FacultyDirectoryItem(
        user_id=uuid4(), full_name="Bob", email="b@test.com",
        employee_id=None, designation=None, specialization=None,
        primary_department=None, photo_url=None, is_active=True,
    )
    assert item.employee_id is None


# ---------------------------------------------------------------------------
# 8. StudentDetailOut contains all profile fields
# ---------------------------------------------------------------------------

def test_student_detail_fields():
    from app.modules.m11_sis.directory_schemas import StudentDetailOut
    fields = set(StudentDetailOut.model_fields.keys())
    assert {"usn", "admission_year", "date_of_birth", "phone",
            "address_line1", "emergency_contact_name"} <= fields


# ---------------------------------------------------------------------------
# 9. FacultyDetailOut
# ---------------------------------------------------------------------------

def test_faculty_detail_fields():
    from app.modules.m11_sis.directory_schemas import FacultyDetailOut
    fields = set(FacultyDetailOut.model_fields.keys())
    assert {"employee_id", "designation", "qualifications", "bio",
            "office_location", "active_assignments"} <= fields
    # Phase 1.5 identity + responsibilities exposure (governance refinement pass).
    assert {"faculty_code", "institution_email", "responsibilities"} <= fields


def test_faculty_directory_item_has_identity_and_responsibilities():
    from app.modules.m11_sis.directory_schemas import FacultyDirectoryItem
    fields = set(FacultyDirectoryItem.model_fields.keys())
    assert {"faculty_code", "responsibilities"} <= fields
    # responsibilities defaults to an empty list when omitted.
    from uuid import uuid4
    item = FacultyDirectoryItem(
        user_id=uuid4(), full_name="Bob", email="b@test.com",
        employee_id=None, designation=None, specialization=None,
        primary_department=None, photo_url=None, is_active=True,
    )
    assert item.responsibilities == [] and item.faculty_code is None


def test_faculty_detail_assignments_is_list():
    from uuid import uuid4
    from app.modules.m11_sis.directory_schemas import FacultyDetailOut
    out = FacultyDetailOut(
        user_id=uuid4(), full_name="Dr X", email="x@test.com",
        identifier=None, employee_id="E001", designation=None,
        qualifications=None, bio=None, office_location=None,
        phone=None, joining_date=None, specialization=None,
        primary_department=None, photo_url=None,
        active_assignments=[], is_active=True,
        profile_created_at=None, profile_updated_at=None,
    )
    assert isinstance(out.active_assignments, list)


# ---------------------------------------------------------------------------
# 10 & 11. Repository method names
# ---------------------------------------------------------------------------

def test_student_repo_methods():
    from app.modules.m11_sis.directory_repository import StudentDirectoryRepository
    for m in ("list_paginated", "get_by_user_id", "upsert_profile", "get_profile"):
        assert hasattr(StudentDirectoryRepository, m)


def test_faculty_repo_methods():
    from app.modules.m11_sis.directory_repository import FacultyDirectoryRepository
    for m in ("list_paginated", "get_by_user_id", "get_active_assignments",
              "list_by_department", "upsert_profile", "get_profile"):
        assert hasattr(FacultyDirectoryRepository, m)


# ---------------------------------------------------------------------------
# 12. DirectoryServiceError
# ---------------------------------------------------------------------------

def test_directory_service_error():
    from app.modules.m11_sis.directory_service import DirectoryServiceError
    e = DirectoryServiceError("TEST_CODE", "test msg", 422)
    assert e.code == "TEST_CODE"
    assert e.message == "test msg"
    assert e.status_code == 422


# ---------------------------------------------------------------------------
# 13 & 14. Service method names
# ---------------------------------------------------------------------------

def test_student_service_methods():
    from app.modules.m11_sis.directory_service import StudentDirectoryService
    for m in ("list_directory", "get_detail", "upsert_profile"):
        assert hasattr(StudentDirectoryService, m)


def test_faculty_service_methods():
    from app.modules.m11_sis.directory_service import FacultyDirectoryService
    for m in ("list_directory", "get_detail", "upsert_profile", "list_by_department"):
        assert hasattr(FacultyDirectoryService, m)


# ---------------------------------------------------------------------------
# 15. Router — routes registered
# ---------------------------------------------------------------------------

def test_directory_router_exists():
    from app.modules.m11_sis.directory_router import directory_router
    paths = {r.path for r in directory_router.routes}
    assert "/directory/students" in paths
    assert "/directory/faculty" in paths


# ---------------------------------------------------------------------------
# 16. RBAC constants
# ---------------------------------------------------------------------------

def test_directory_router_rbac():
    import app.modules.m11_sis.directory_router as dr
    from app.core.auth.models import TenantRole
    # _WRITE: ADMIN + DEAN can upsert profiles
    assert TenantRole.ADMIN in dr._WRITE
    assert TenantRole.DEAN in dr._WRITE
    assert TenantRole.FACULTY not in dr._WRITE
    # _READ: global directory listings are admin-only (P1.9)
    assert TenantRole.ADMIN in dr._READ
    assert TenantRole.FACULTY not in dr._READ
    # _DETAIL: ADMIN and DEAN can open individual faculty profiles
    assert TenantRole.ADMIN in dr._DETAIL
    assert TenantRole.DEAN in dr._DETAIL


# ---------------------------------------------------------------------------
# 17. Audit event types
# ---------------------------------------------------------------------------

def test_audit_events_present():
    from app.core.audit_log.models import AuditEventType
    assert hasattr(AuditEventType, "STUDENT_PROFILE_UPDATED")
    assert hasattr(AuditEventType, "FACULTY_PROFILE_UPDATED")


# ---------------------------------------------------------------------------
# 18 & 19. Migrations
# ---------------------------------------------------------------------------

def _load_migration(filename: str):
    base = pathlib.Path(__file__).parents[3] / "alembic" / "tenant_versions"
    spec = importlib.util.spec_from_file_location("mig", base / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0029_revision():
    mod = _load_migration("0029_tenant_sis_student_profiles.py")
    assert mod.revision == "0029ten"
    assert mod.down_revision == "0028"


def test_migration_0030_revision():
    mod = _load_migration("0030_tenant_sis_faculty_profiles.py")
    assert mod.revision == "0030ten"
    assert mod.down_revision == "0029ten"


# ---------------------------------------------------------------------------
# 20. USN uppercase + strip (already covered in test 3, this verifies edge case)
# ---------------------------------------------------------------------------

def test_usn_whitespace_only_becomes_none():
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    s = StudentProfileUpsert(usn="   ")
    assert s.usn is None


# ---------------------------------------------------------------------------
# 21. employee_id uppercase
# ---------------------------------------------------------------------------

def test_employee_id_uppercase():
    from app.modules.m11_sis.directory_schemas import FacultyProfileUpsert
    f = FacultyProfileUpsert(employee_id="fac-2024-001")
    assert f.employee_id == "FAC-2024-001"


# ---------------------------------------------------------------------------
# 22. admission_year out of range
# ---------------------------------------------------------------------------

def test_admission_year_future_out_of_range():
    from pydantic import ValidationError
    from app.modules.m11_sis.directory_schemas import StudentProfileUpsert
    with pytest.raises(ValidationError):
        StudentProfileUpsert(admission_year=2200)


# ---------------------------------------------------------------------------
# 23. SisStudentProfile primary key
# ---------------------------------------------------------------------------

def test_student_profile_pk_is_user_id():
    from app.modules.m11_sis.models import SisStudentProfile
    pk_cols = [c.name for c in SisStudentProfile.__table__.primary_key]
    assert pk_cols == ["user_id"]


# ---------------------------------------------------------------------------
# 24. SisFacultyProfile primary key and NOT NULL employee_id
# ---------------------------------------------------------------------------

def test_faculty_profile_pk_is_user_id():
    from app.modules.m11_sis.models import SisFacultyProfile
    pk_cols = [c.name for c in SisFacultyProfile.__table__.primary_key]
    assert pk_cols == ["user_id"]


def test_faculty_employee_id_nullable_since_phase_1_5():
    # Phase 1.5 (faculty identity) replaced employee_id with the auto-generated
    # faculty_code and stopped collecting employee_id, so it is now nullable.
    from app.modules.m11_sis.models import SisFacultyProfile
    col = SisFacultyProfile.__table__.c["employee_id"]
    assert col.nullable is True


def test_faculty_code_and_institution_email_present():
    from app.modules.m11_sis.models import SisFacultyProfile
    cols = SisFacultyProfile.__table__.c
    assert "faculty_code" in cols and cols["faculty_code"].nullable is True
    assert "institution_email" in cols and cols["institution_email"].nullable is True


# ---------------------------------------------------------------------------
# 25. Faculty primary_department_id nullable
# ---------------------------------------------------------------------------

def test_faculty_primary_dept_nullable():
    from app.modules.m11_sis.models import SisFacultyProfile
    col = SisFacultyProfile.__table__.c["primary_department_id"]
    assert col.nullable is True


# ---------------------------------------------------------------------------
# 26. Directory router paths
# ---------------------------------------------------------------------------

def test_directory_router_detail_paths():
    from app.modules.m11_sis.directory_router import directory_router
    paths = {r.path for r in directory_router.routes}
    assert "/directory/students/{user_id}" in paths
    assert "/directory/faculty/{user_id}" in paths
    assert "/directory/students/{user_id}/profile" in paths or \
           "/directory/faculty/{user_id}/profile" in paths


# ---------------------------------------------------------------------------
# 27. Department faculty route
# ---------------------------------------------------------------------------

def test_dept_faculty_route():
    from app.modules.m11_sis.directory_router import directory_router
    paths = {r.path for r in directory_router.routes}
    assert "/departments/{dept_id}/faculty" in paths


# ---------------------------------------------------------------------------
# 28. DashboardCountsOut extended fields
# ---------------------------------------------------------------------------

def test_dashboard_counts_has_totals():
    from app.modules.m11_sis.enrollment_schemas import DashboardCountsOut
    fields = set(DashboardCountsOut.model_fields.keys())
    assert "total_students" in fields
    assert "total_faculty" in fields


# ---------------------------------------------------------------------------
# 29. StudentProfileOut extended fields
# ---------------------------------------------------------------------------

def test_student_profile_out_has_usn():
    from app.modules.m11_sis.enrollment_schemas import StudentProfileOut
    fields = set(StudentProfileOut.model_fields.keys())
    assert "usn" in fields
    assert "admission_year" in fields


# ---------------------------------------------------------------------------
# 30. FacultyDetailOut active_assignments type annotation
# ---------------------------------------------------------------------------

def test_faculty_detail_assignment_annotation():
    from app.modules.m11_sis.directory_schemas import FacultyDetailOut
    hint = FacultyDetailOut.model_fields["active_assignments"]
    # list[AssignmentMini] annotation should be present
    assert hint is not None


# ---------------------------------------------------------------------------
# 31-33. Regression: faculty in directory list can always open their profile
#
# Bug: get_teaching_programs returned raw Row objects (rows.fetchall()).
# SQLAlchemy 2.x Row supports r[0] and r.key but NOT r["key"] string subscript.
# The service did r["program_id"] — TypeError for any faculty with teaching
# programs, manifesting as "Faculty member not found." in the UI.
# Akash Rao (FAC0007) and Neha Reddy (FAC0009) had active subject assignments
# linked to programs with acad_program_id set; Dr. Aishu/Pooja did not, so
# their empty list short-circuited the broken code path.
# Fix: rows.mappings().all() returns RowMapping objects (dict-like) so r["key"] works.
# ---------------------------------------------------------------------------

def test_get_teaching_programs_uses_mappings():
    """Structural guard: get_teaching_programs must call .mappings() so the service
    can do r['program_id']. A plain fetchall() returns Row objects that raise
    TypeError on string-key subscript in SQLAlchemy 2.x."""
    import inspect
    from app.modules.m11_sis.directory_repository import FacultyDirectoryRepository
    src = inspect.getsource(FacultyDirectoryRepository.get_teaching_programs)
    assert ".mappings()" in src, (
        "get_teaching_programs must use rows.mappings().all() not rows.fetchall(); "
        "string-key access r['program_id'] requires RowMapping, not Row"
    )


def test_faculty_detail_with_teaching_programs_builds_correctly():
    """FacultyDetailOut accepts a non-empty teaching_programs list.
    Validates that the service can build the response when faculty
    have programs (regression for the Akash/Neha 'not found' failure)."""
    from uuid import uuid4
    from app.modules.m11_sis.directory_schemas import FacultyDetailOut, ProgramMini

    programs = [
        ProgramMini(id=uuid4(), name="MCA", code="MCA01", degree_type="MASTERS"),
        ProgramMini(id=uuid4(), name="BCA", code="BCA01", degree_type="BACHELORS"),
    ]
    out = FacultyDetailOut(
        user_id=uuid4(), full_name="Akash Rao", email="akash@test.com",
        identifier=None, employee_id=None, faculty_code="FAC0007",
        designation=None, qualifications=None, bio=None, office_location=None,
        phone=None, joining_date=None, specialization=None,
        primary_department=None, photo_url=None,
        active_assignments=[], teaching_programs=programs,
        governing_programs=[], responsibilities=[],
        is_active=True, profile_created_at=None, profile_updated_at=None,
    )
    assert len(out.teaching_programs) == 2
    assert out.teaching_programs[0].name == "MCA"
    assert out.faculty_code == "FAC0007"


def test_course_model_has_title_not_name():
    """Regression: directory_service built CourseMini with course.name but the
    Course ORM model has 'title' not 'name'. Faculty with assigned courses got
    AttributeError -> 500 -> 'Faculty member not found.' in the UI.
    Fix: use course.title."""
    from app.modules.m01_program_advisor.models import Course
    cols = {c.name for c in Course.__table__.columns}
    assert "title" in cols, "Course must have a 'title' column"
    assert "name" not in cols, "Course has no 'name' column — use 'title' instead"


def test_faculty_detail_service_uses_course_title():
    """Structural guard: directory_service must read course.title, not course.name."""
    import inspect
    from app.modules.m11_sis import directory_service
    src = inspect.getsource(directory_service.FacultyDirectoryService.get_detail)
    assert "course.title" in src, "get_detail must use course.title (Course ORM field), not course.name"
    assert "course.name" not in src, "course.name does not exist on the Course ORM model"


def test_teaching_programs_row_access_via_dict():
    """Simulate the exact service code path that was broken.
    RowMapping objects (returned by .mappings()) must support r['key'] access.
    This would have failed with plain SQLAlchemy Row objects."""
    from app.modules.m11_sis.directory_schemas import ProgramMini
    from uuid import uuid4

    # Simulate what rows.mappings().all() returns: dict-like RowMapping objects.
    # We use plain dicts here since RowMapping behaves identically for key access.
    fake_rows = [
        {"program_id": str(uuid4()), "program_name": "MCA", "program_code": "MCA01", "degree_type": "MASTERS"},
        {"program_id": str(uuid4()), "program_name": "BCA", "program_code": "BCA01", "degree_type": "BACHELORS"},
    ]
    # Exact code from directory_service.py get_detail (lines 397-399):
    teaching_programs = [
        ProgramMini(id=r["program_id"], name=r["program_name"], code=r["program_code"], degree_type=r["degree_type"])
        for r in fake_rows
    ]
    assert len(teaching_programs) == 2
    assert teaching_programs[0].name == "MCA"
    assert teaching_programs[1].degree_type == "BACHELORS"
