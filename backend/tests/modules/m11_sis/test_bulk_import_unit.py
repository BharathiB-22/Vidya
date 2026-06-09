"""
Unit tests — H53 SIS Bulk Profile Import

No live database. All tests use import + assert.

Coverage:
  1.  ProfileImportRowResult — required fields present
  2.  ProfileImportRowResult — optional profile fields present
  3.  ProfileImportPreviewResponse — counter fields present
  4.  ProfileImportCommitResult — updated/skipped/errors (not created)
  5.  BulkProfileImportService — preview and commit static methods exist
  6.  BulkProfileImportService — _parse_row is a static method
  7.  BulkProfileImportService — _resolve_students is a static method
  8.  BulkProfileImportService — _check_usn_db_uniqueness is a static method
  9.  Route: POST /directory/students/import/preview registered
 10.  Route: POST /directory/students/import/commit registered
 11.  Route: GET  /directory/students/import/template.csv registered
 12.  Route: GET  /directory/students/import/template.xlsx registered
 13.  RBAC: preview endpoint requires ADMIN or DEAN (inspect source)
 14.  RBAC: commit endpoint requires ADMIN or DEAN (inspect source)
 15.  Source: commit calls StudentDirectoryService.upsert_profile
 16.  Source: preview delegates file parsing to OnboardingService._parse_file
 17.  Source: within-file USN duplicate detection present
 18.  Source: DB USN uniqueness check present
 19.  Source: at-least-one-profile-field check present
 20.  SIS router total route count updated to 27
 21.  _parse_row: email-only row is marked invalid (no profile fields)
 22.  _parse_row: invalid email format returns error
 23.  _parse_row: admission_year out-of-range returns error
 24.  _parse_row: valid row with usn + admission_year is marked valid
 25.  _parse_row: duplicate USN within file flagged
"""
import inspect

import pytest


# ---------------------------------------------------------------------------
# 1–4. Schema field presence
# ---------------------------------------------------------------------------

def test_profile_import_row_result_core_fields():
    from app.modules.m11_sis.bulk_import_schemas import ProfileImportRowResult
    fields = set(ProfileImportRowResult.model_fields)
    assert {"row_number", "email", "is_valid", "errors", "student_id", "student_name"} <= fields


def test_profile_import_row_result_profile_fields():
    from app.modules.m11_sis.bulk_import_schemas import ProfileImportRowResult
    fields = set(ProfileImportRowResult.model_fields)
    assert {"usn", "admission_year", "phone", "address_line1", "address_city",
            "address_state", "emergency_contact_name", "emergency_contact_phone"} <= fields


def test_profile_import_preview_response_counter_fields():
    from app.modules.m11_sis.bulk_import_schemas import ProfileImportPreviewResponse
    fields = set(ProfileImportPreviewResponse.model_fields)
    assert {
        "total_rows", "valid_rows", "invalid_rows",
        "not_found_in_db", "duplicate_email_in_file",
        "duplicate_usn_in_file", "duplicate_usn_in_db", "rows",
    } <= fields


def test_profile_import_commit_result_has_updated_not_created():
    from app.modules.m11_sis.bulk_import_schemas import ProfileImportCommitResult
    fields = set(ProfileImportCommitResult.model_fields)
    assert {"total", "updated", "skipped", "errors"} <= fields
    assert "created" not in fields


# ---------------------------------------------------------------------------
# 5–8. Service method existence
# ---------------------------------------------------------------------------

def test_bulk_import_service_has_preview():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    assert callable(getattr(BulkProfileImportService, "preview", None))


def test_bulk_import_service_has_commit():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    assert callable(getattr(BulkProfileImportService, "commit", None))


def test_bulk_import_service_has_parse_row():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    assert callable(getattr(BulkProfileImportService, "_parse_row", None))


def test_bulk_import_service_has_resolve_students():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    assert callable(getattr(BulkProfileImportService, "_resolve_students", None))


# ---------------------------------------------------------------------------
# 9–12. Routes registered in directory_router
# ---------------------------------------------------------------------------

def _dir_routes():
    from app.modules.m11_sis.directory_router import directory_router
    return {(frozenset(getattr(r, "methods", set())), r.path) for r in directory_router.routes}


def test_bulk_import_preview_route_registered():
    routes = _dir_routes()
    assert (frozenset({"POST"}), "/directory/students/import/preview") in routes


def test_bulk_import_commit_route_registered():
    routes = _dir_routes()
    assert (frozenset({"POST"}), "/directory/students/import/commit") in routes


def test_bulk_import_template_csv_route_registered():
    routes = _dir_routes()
    assert (frozenset({"GET"}), "/directory/students/import/template.csv") in routes


def test_bulk_import_template_xlsx_route_registered():
    routes = _dir_routes()
    assert (frozenset({"GET"}), "/directory/students/import/template.xlsx") in routes


# ---------------------------------------------------------------------------
# 13–14. RBAC: _WRITE = ADMIN, DEAN
# ---------------------------------------------------------------------------

def test_bulk_import_preview_uses_write_gate():
    import app.modules.m11_sis.directory_router as dr
    src = inspect.getsource(dr.bulk_profile_import_preview)
    assert "require_roles" in src
    assert "_WRITE" in src


def test_bulk_import_commit_uses_write_gate():
    import app.modules.m11_sis.directory_router as dr
    src = inspect.getsource(dr.bulk_profile_import_commit)
    assert "require_roles" in src
    assert "_WRITE" in src


# ---------------------------------------------------------------------------
# 15–19. Source-level wiring checks
# ---------------------------------------------------------------------------

def test_commit_calls_upsert_profile():
    import app.modules.m11_sis.bulk_import_service as svc
    src = inspect.getsource(svc.BulkProfileImportService.commit)
    assert "upsert_profile" in src
    assert "StudentDirectoryService" in src


def test_preview_delegates_to_onboarding_parse():
    import app.modules.m11_sis.bulk_import_service as svc
    src = inspect.getsource(svc.BulkProfileImportService._parse_file)
    assert "OnboardingService._parse_file" in src


def test_preview_has_within_file_usn_dup_check():
    import app.modules.m11_sis.bulk_import_service as svc
    src = inspect.getsource(svc.BulkProfileImportService._parse_row)
    assert "seen_usns" in src
    assert "duplicate USN within this file" in src


def test_preview_has_db_usn_uniqueness_check():
    import app.modules.m11_sis.bulk_import_service as svc
    src = inspect.getsource(svc.BulkProfileImportService._check_usn_db_uniqueness)
    assert "sis_student_profiles" in src


def test_preview_has_at_least_one_field_check():
    import app.modules.m11_sis.bulk_import_service as svc
    src = inspect.getsource(svc.BulkProfileImportService._parse_row)
    assert "no profile fields provided" in src


# ---------------------------------------------------------------------------
# 20. SIS router total route count = 27
# ---------------------------------------------------------------------------

def test_sis_router_total_route_count():
    from app.modules.m11_sis.router import router
    # 5 school + 7 enrollment + 11 directory + 4 me + 2 rollover + 15 attendance
    # + 19 marks + 10 hallticket + 24 exam + 36 results + 2 import_batches (H64.1) = 166
    assert len(router.routes) == 176


# ---------------------------------------------------------------------------
# 21–25. _parse_row unit behaviour (no DB required)
# ---------------------------------------------------------------------------

def test_parse_row_email_only_is_invalid():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    row, _, _ = BulkProfileImportService._parse_row(1, {"email": "a@b.com"}, set(), set())
    assert not row.is_valid
    assert any("no profile fields" in e for e in row.errors)


def test_parse_row_invalid_email_format():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    row, _, _ = BulkProfileImportService._parse_row(
        1, {"email": "not-an-email", "usn": "USN001"}, set(), set()
    )
    assert not row.is_valid
    assert any("valid email" in e for e in row.errors)


def test_parse_row_admission_year_out_of_range():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    row, _, _ = BulkProfileImportService._parse_row(
        1, {"email": "a@b.com", "usn": "USN001", "admission_year": "1800"}, set(), set()
    )
    assert not row.is_valid
    assert any("range" in e for e in row.errors)


def test_parse_row_valid_row():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    row, de, du = BulkProfileImportService._parse_row(
        1,
        {"email": "student@test.com", "usn": "1DS22CS001", "admission_year": "2022"},
        set(),
        set(),
    )
    assert row.is_valid, row.errors
    assert row.usn == "1DS22CS001"
    assert row.admission_year == 2022
    assert not de
    assert not du


def test_parse_row_duplicate_usn_in_file():
    from app.modules.m11_sis.bulk_import_service import BulkProfileImportService
    seen_usns = {"1DS22CS001"}
    row, _, dup_usn = BulkProfileImportService._parse_row(
        2,
        {"email": "other@test.com", "usn": "1DS22CS001"},
        set(),
        seen_usns,
    )
    assert not row.is_valid
    assert dup_usn
    assert any("duplicate USN" in e for e in row.errors)
