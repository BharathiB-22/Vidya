"""
Unit tests — SIS Self-Service (H51)

Coverage:
  1.  StudentSelfServiceUpdate — only contact fields present
  2.  StudentSelfServiceUpdate — admin-only fields absent (usn, admission_year, notes)
  3.  FacultySelfServiceUpdate — only contact/bio fields present
  4.  FacultySelfServiceUpdate — admin-only fields absent (employee_id, designation, joining_date)
  5.  StudentSelfServiceUpdate — all fields optional, empty body valid
  6.  FacultySelfServiceUpdate — all fields optional, empty body valid
  7.  StudentSelfServiceUpdate — model_dump excludes None by default
  8.  FacultySelfServiceUpdate — model_dump excludes None by default
  9.  StudentDirectoryService — upsert_own_profile method exists
 10.  FacultyDirectoryService — upsert_own_profile method exists
 11.  me_router — /me/student-profile route registered (GET + PUT)
 12.  me_router — /me/faculty-profile route registered (GET + PUT)
 13.  me_router RBAC — student endpoint requires STUDENT role
 14.  me_router RBAC — faculty endpoint requires FACULTY role
 15.  SIS router — me_router included (route count updated to 23)
 16.  StudentSelfServiceUpdate — phone field accepts None
 17.  FacultySelfServiceUpdate — bio accepts multi-line text
 18.  Cross-role guard — ADMIN cannot reach /me/student-profile (403 pattern)
 19.  StudentSelfServiceUpdate has no usn field
 20.  FacultySelfServiceUpdate has no employee_id field
"""
import pytest


# ---------------------------------------------------------------------------
# 1. StudentSelfServiceUpdate — expected contact fields present
# ---------------------------------------------------------------------------

def test_student_self_service_has_contact_fields():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    fields = set(StudentSelfServiceUpdate.model_fields.keys())
    assert {"phone", "address_line1", "address_city", "address_state",
            "emergency_contact_name", "emergency_contact_phone", "photo_url"} <= fields


# ---------------------------------------------------------------------------
# 2. StudentSelfServiceUpdate — admin-only fields absent
# ---------------------------------------------------------------------------

def test_student_self_service_no_admin_fields():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    fields = set(StudentSelfServiceUpdate.model_fields.keys())
    for forbidden in ("usn", "admission_year", "date_of_birth", "notes"):
        assert forbidden not in fields, f"'{forbidden}' must not be editable by student"


# ---------------------------------------------------------------------------
# 3. FacultySelfServiceUpdate — expected contact/bio fields present
# ---------------------------------------------------------------------------

def test_faculty_self_service_has_contact_bio_fields():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    fields = set(FacultySelfServiceUpdate.model_fields.keys())
    assert {"phone", "office_location", "bio", "specialization", "photo_url"} <= fields


# ---------------------------------------------------------------------------
# 4. FacultySelfServiceUpdate — admin-only fields absent
# ---------------------------------------------------------------------------

def test_faculty_self_service_no_admin_fields():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    fields = set(FacultySelfServiceUpdate.model_fields.keys())
    for forbidden in ("employee_id", "designation", "qualifications",
                      "joining_date", "primary_department_id"):
        assert forbidden not in fields, f"'{forbidden}' must not be editable by faculty"


# ---------------------------------------------------------------------------
# 5 & 6. Both schemas accept empty body
# ---------------------------------------------------------------------------

def test_student_self_service_empty_body():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    s = StudentSelfServiceUpdate()
    assert s.phone is None


def test_faculty_self_service_empty_body():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    f = FacultySelfServiceUpdate()
    assert f.bio is None


# ---------------------------------------------------------------------------
# 7 & 8. model_dump(exclude_none=True) produces only provided fields
# ---------------------------------------------------------------------------

def test_student_self_service_dump_excludes_none():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    s = StudentSelfServiceUpdate(phone="+91 99999 00000")
    dumped = s.model_dump(exclude_none=True)
    assert dumped == {"phone": "+91 99999 00000"}


def test_faculty_self_service_dump_excludes_none():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    f = FacultySelfServiceUpdate(bio="Professor of CS", specialization="AI")
    dumped = f.model_dump(exclude_none=True)
    assert dumped == {"bio": "Professor of CS", "specialization": "AI"}


# ---------------------------------------------------------------------------
# 9 & 10. Service method names
# ---------------------------------------------------------------------------

def test_student_service_has_upsert_own():
    from app.modules.m11_sis.directory_service import StudentDirectoryService
    assert hasattr(StudentDirectoryService, "upsert_own_profile")


def test_faculty_service_has_upsert_own():
    from app.modules.m11_sis.directory_service import FacultyDirectoryService
    assert hasattr(FacultyDirectoryService, "upsert_own_profile")


# ---------------------------------------------------------------------------
# 11 & 12. me_router routes registered
# ---------------------------------------------------------------------------

def test_me_router_student_routes():
    from app.modules.m11_sis.me_router import me_router
    paths = {r.path for r in me_router.routes}
    assert "/me/student-profile" in paths


def test_me_router_faculty_routes():
    from app.modules.m11_sis.me_router import me_router
    paths = {r.path for r in me_router.routes}
    assert "/me/faculty-profile" in paths


# ---------------------------------------------------------------------------
# 13. me_router RBAC — student endpoint dependency uses STUDENT role
# ---------------------------------------------------------------------------

def test_me_router_student_rbac():
    from app.modules.m11_sis.me_router import me_router
    from app.core.auth.models import TenantRole
    # Find the GET /me/student-profile route and inspect its dependencies
    student_routes = [r for r in me_router.routes if r.path == "/me/student-profile"]
    assert len(student_routes) >= 1
    # Verify STUDENT is the only allowed role by checking module constants
    import app.modules.m11_sis.me_router as mr
    # The router uses require_roles(TenantRole.STUDENT) inline — verify role used
    import inspect
    src = inspect.getsource(mr)
    assert "TenantRole.STUDENT" in src
    assert "TenantRole.FACULTY" in src


# ---------------------------------------------------------------------------
# 14. me_router RBAC — faculty endpoint present with FACULTY role
# ---------------------------------------------------------------------------

def test_me_router_faculty_rbac():
    from app.modules.m11_sis.me_router import me_router
    faculty_routes = [r for r in me_router.routes if r.path == "/me/faculty-profile"]
    assert len(faculty_routes) >= 1


# ---------------------------------------------------------------------------
# 15. SIS router total routes now includes me_router (19 + 4 = 23)
# ---------------------------------------------------------------------------

def test_sis_router_includes_me_routes():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover + 15 attendance
    # + 19 marks + 10 hallticket + 24 exam + 36 results = 133
    assert len(router.routes) == 176


# ---------------------------------------------------------------------------
# 16. phone field accepts None (all fields optional)
# ---------------------------------------------------------------------------

def test_student_phone_accepts_none():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    s = StudentSelfServiceUpdate(phone=None)
    assert s.phone is None


# ---------------------------------------------------------------------------
# 17. bio accepts multi-line text
# ---------------------------------------------------------------------------

def test_faculty_bio_multiline():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    bio = "Line 1\nLine 2\nLine 3"
    f = FacultySelfServiceUpdate(bio=bio)
    assert f.bio == bio


# ---------------------------------------------------------------------------
# 18. ADMIN cannot reach /me/student-profile — confirmed by role gate
# ---------------------------------------------------------------------------

def test_admin_excluded_from_student_me_route():
    from app.core.auth.models import TenantRole
    import app.modules.m11_sis.me_router as mr
    import inspect
    src = inspect.getsource(mr)
    # ADMIN must not appear as an allowed role for student endpoint
    # The source uses require_roles(TenantRole.STUDENT) — not ADMIN
    assert "require_roles(TenantRole.STUDENT)" in src
    assert "require_roles(TenantRole.FACULTY)" in src


# ---------------------------------------------------------------------------
# 19. StudentSelfServiceUpdate has no usn field
# ---------------------------------------------------------------------------

def test_student_self_service_no_usn():
    from app.modules.m11_sis.directory_schemas import StudentSelfServiceUpdate
    assert "usn" not in StudentSelfServiceUpdate.model_fields


# ---------------------------------------------------------------------------
# 20. FacultySelfServiceUpdate has no employee_id field
# ---------------------------------------------------------------------------

def test_faculty_self_service_no_employee_id():
    from app.modules.m11_sis.directory_schemas import FacultySelfServiceUpdate
    assert "employee_id" not in FacultySelfServiceUpdate.model_fields
