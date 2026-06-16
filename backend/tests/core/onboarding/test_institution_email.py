"""Unit tests — Institution Email Foundation (Phase 1.2 / Task C)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.onboarding.institution_email_schemas import (
    SetInstitutionDomainIn,
    normalize_domain,
)
from app.core.onboarding.institution_email_service import (
    InstitutionEmailError,
    InstitutionEmailService,
    format_email,
)


# ---------------------------------------------------------------------------
# 1. Generation helpers
# ---------------------------------------------------------------------------

def test_format_email_student_lowercases():
    assert format_email("SCA26BCA001", "lms.edu") == "sca26bca001@lms.edu"


def test_format_email_uppercase_domain_normalized():
    assert format_email("SCA26BCA002", "LMS.EDU") == "sca26bca002@lms.edu"


def test_format_email_strips_and_normalizes_domain():
    assert format_email("  emp001 ", "@lms.edu") == "emp001@lms.edu"


def test_normalize_domain():
    assert normalize_domain("  @LMS.edu ") == "lms.edu"


# ---------------------------------------------------------------------------
# 2. Domain validation
# ---------------------------------------------------------------------------

def test_set_domain_valid():
    assert SetInstitutionDomainIn(domain="LMS.edu").domain == "lms.edu"


def test_set_domain_rejects_garbage():
    with pytest.raises(Exception):
        SetInstitutionDomainIn(domain="not a domain")


def test_set_domain_rejects_no_tld():
    with pytest.raises(Exception):
        SetInstitutionDomainIn(domain="localhost")


# ---------------------------------------------------------------------------
# 3. Preview classification (DB access patched out)
# ---------------------------------------------------------------------------

def _student(usn, inst=None):
    return {"user_id": uuid.uuid4(), "full_name": "Stu",
            "login_email": "stu@gmail.com", "existing_inst": inst, "usn": usn}


@pytest.mark.asyncio
async def test_preview_classifies_rows():
    rows = [
        _student("SCA26BCA001"),                              # ASSIGN
        _student(None),                                       # SKIP_NO_IDENTIFIER
        _student("SCA26BCA002", inst="sca26bca002@lms.edu"),  # SKIP_HAS_EMAIL
        _student("SCA26BCA003"),                              # ASSIGN
    ]
    with patch.object(InstitutionEmailService, "_load", AsyncMock(return_value=rows)):
        resp = await InstitutionEmailService.preview(
            MagicMock(), schema_name="t", override_domain="lms.edu"
        )
    by_action = {r.action for r in resp.rows}
    assert resp.domain == "lms.edu"
    assert resp.total_students == 4
    assert resp.to_assign == 2
    assert resp.already_have == 1
    assert resp.no_identifier == 1
    assert {"ASSIGN", "SKIP_NO_IDENTIFIER", "SKIP_HAS_EMAIL"} <= by_action
    assign = next(r for r in resp.rows if r.action == "ASSIGN")
    assert assign.projected_institution_email == "sca26bca001@lms.edu"


@pytest.mark.asyncio
async def test_preview_detects_conflict_against_existing():
    # An existing institution_email collides with a projected one.
    rows = [
        _student("SCA26BCA001", inst="sca26bca001@lms.edu"),  # already taken
        _student("SCA26BCA001"),                              # projects same → CONFLICT
    ]
    with patch.object(InstitutionEmailService, "_load", AsyncMock(return_value=rows)):
        resp = await InstitutionEmailService.preview(
            MagicMock(), schema_name="t", override_domain="lms.edu"
        )
    assert resp.conflicts == 1
    assert any(r.action == "CONFLICT" for r in resp.rows)


@pytest.mark.asyncio
async def test_preview_requires_domain():
    get_dom = AsyncMock(return_value=MagicMock(institution_domain=None))
    with patch.object(InstitutionEmailService, "get_domain", get_dom):
        with pytest.raises(InstitutionEmailError) as exc:
            await InstitutionEmailService.preview(MagicMock(), schema_name="t", override_domain=None)
    assert exc.value.code == "NO_DOMAIN"
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# 4. Commit writes only missing emails (DB patched)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_commit_assigns_and_skips():
    rows = [
        _student("SCA26BCA001"),                              # ASSIGN
        _student("SCA26BCA002", inst="sca26bca002@lms.edu"),  # SKIP (already has)
        _student(None),                                       # SKIP (no identifier)
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    fake_batch = MagicMock(batch_ref="IMPORT-X")
    with patch.object(InstitutionEmailService, "_load", AsyncMock(return_value=rows)), \
         patch("app.modules.m11_sis.import_batch_service.ImportBatchService.create_batch",
               AsyncMock(return_value=fake_batch)):
        result = await InstitutionEmailService.commit(
            db, schema_name="t", actor_user_id=uuid.uuid4(), override_domain="lms.edu"
        )
    assert result.assigned == 1
    assert result.skipped == 2
    assert result.batch_ref == "IMPORT-X"
    assert result.domain == "lms.edu"
