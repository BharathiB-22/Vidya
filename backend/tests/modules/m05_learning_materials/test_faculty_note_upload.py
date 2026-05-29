"""
Tests for M05 faculty note upload: text extraction, service logic, and router endpoint.

Coverage:
  - _extract_text(): PDF via pypdf stub, TXT, DOCX via python-docx stub
  - ingest_faculty_note(): validation guards, dedup, item creation
  - POST /{package_id}/notes: RBAC (FACULTY=201, STUDENT=403), content-type guard
"""
from __future__ import annotations

import io
import uuid
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _extract_text — pure function, no DB
# ---------------------------------------------------------------------------

class TestExtractText:
    """Unit tests for the private _extract_text helper in service.py."""

    def _fn(self, file_bytes: bytes, content_type: str) -> str:
        from app.modules.m05_learning_materials.service import _extract_text
        return _extract_text(file_bytes, content_type)

    def test_plain_utf8(self):
        text = "Hello, this is plain text."
        result = self._fn(text.encode("utf-8"), "text/plain")
        assert "Hello" in result

    def test_plain_latin1_fallback(self):
        # Latin-1 encoded byte that is invalid UTF-8
        raw = b"caf\xe9 au lait"
        result = self._fn(raw, "text/plain")
        assert result  # should not raise

    def test_unknown_type_returns_empty(self):
        result = self._fn(b"some data", "application/octet-stream")
        assert result == ""

    def test_pdf_stub(self):
        """Stub pypdf so the PDF path is exercised without a real PDF."""
        # Create a minimal stub for pypdf.PdfReader
        page_stub = MagicMock()
        page_stub.extract_text.return_value = "Machine Learning Introduction"
        reader_stub = MagicMock()
        reader_stub.pages = [page_stub]

        pdf_module = ModuleType("pypdf")
        pdf_module.PdfReader = MagicMock(return_value=reader_stub)

        with patch.dict("sys.modules", {"pypdf": pdf_module}):
            result = self._fn(b"%PDF-stub", "application/pdf")

        assert "Machine Learning" in result

    def test_pdf_extraction_failure_returns_empty(self):
        """If pypdf raises, _extract_text returns '' — caller raises EMPTY_CONTENT."""
        broken_pdf = MagicMock()
        broken_pdf.PdfReader = MagicMock(side_effect=Exception("broken pdf"))

        with patch.dict("sys.modules", {"pypdf": broken_pdf}):
            result = self._fn(b"not a real pdf", "application/pdf")

        assert result == ""

    def test_docx_stub(self):
        """Stub python-docx so DOCX extraction path is exercised."""
        para1 = MagicMock()
        para1.text = "Unit 1: Introduction to Algorithms"
        para2 = MagicMock()
        para2.text = ""  # empty paragraph — should be skipped
        para3 = MagicMock()
        para3.text = "Sorting and Searching techniques."

        doc_stub = MagicMock()
        doc_stub.paragraphs = [para1, para2, para3]
        docx_module = ModuleType("docx")
        docx_module.Document = MagicMock(return_value=doc_stub)

        with patch.dict("sys.modules", {"docx": docx_module}):
            result = self._fn(
                b"PK...",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        assert "Introduction to Algorithms" in result
        assert "Sorting and Searching" in result
        # Empty paragraph not in output
        assert result.count("\n") == 1  # two non-empty paras joined by one \n


# ---------------------------------------------------------------------------
# ingest_faculty_note — service-level unit tests (no DB)
# ---------------------------------------------------------------------------

def _make_pkg(item_count: int = 0, status: str = "READY"):
    pkg = MagicMock()
    pkg.id = uuid.uuid4()
    pkg.item_count = item_count
    pkg.status = MagicMock()
    pkg.status.value = status
    return pkg


def _make_item():
    item = MagicMock()
    item.id = uuid.uuid4()
    item.metadata_ = {"word_count": 10, "storage_key": None}
    return item


class TestIngestFacultyNote:
    """Service-level unit tests. DB and S3 are fully mocked."""

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self):
        from app.modules.m05_learning_materials.service import (
            LearningPackageService, PackageServiceError
        )
        mock_db = AsyncMock()
        with pytest.raises(PackageServiceError) as exc_info:
            await LearningPackageService.ingest_faculty_note(
                package_id=uuid.uuid4(),
                file_bytes=b"some data",
                filename="test.exe",
                content_type="application/x-msdownload",
                title=None,
                added_by=uuid.uuid4(),
                tenant_slug="test-uni",
                db=mock_db,
            )
        assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"
        assert exc_info.value.status_code == 415

    @pytest.mark.asyncio
    async def test_file_too_large_raises(self):
        from app.modules.m05_learning_materials.service import (
            LearningPackageService, PackageServiceError
        )
        mock_db = AsyncMock()
        big_bytes = b"x" * (21 * 1024 * 1024)  # 21 MB
        with pytest.raises(PackageServiceError) as exc_info:
            await LearningPackageService.ingest_faculty_note(
                package_id=uuid.uuid4(),
                file_bytes=big_bytes,
                filename="huge.pdf",
                content_type="application/pdf",
                title=None,
                added_by=uuid.uuid4(),
                tenant_slug="test-uni",
                db=mock_db,
            )
        assert exc_info.value.code == "FILE_TOO_LARGE"
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_empty_content_raises(self):
        from app.modules.m05_learning_materials.service import (
            LearningPackageService, PackageServiceError
        )
        mock_db = AsyncMock()
        empty_txt = b"   "  # only whitespace
        # Patch _require_mutable to return a mock package
        pkg = _make_pkg()
        with (
            patch(
                "app.modules.m05_learning_materials.service._require_mutable",
                new=AsyncMock(return_value=pkg),
            ),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.ingest_faculty_note(
                    package_id=pkg.id,
                    file_bytes=empty_txt,
                    filename="empty.txt",
                    content_type="text/plain",
                    title=None,
                    added_by=uuid.uuid4(),
                    tenant_slug="test-uni",
                    db=mock_db,
                )
        assert exc_info.value.code == "EMPTY_CONTENT"
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_successful_ingest_creates_item(self):
        from app.modules.m05_learning_materials.service import (
            LearningPackageService,
        )
        from app.modules.m05_learning_materials.repository import PackageItemRepository

        mock_db = AsyncMock()
        pkg = _make_pkg(item_count=3)
        item = _make_item()
        txt_bytes = b"Introduction to Neural Networks. Deep learning is a subset of machine learning."

        bulk_create_mock = AsyncMock(return_value=[item])

        with (
            patch(
                "app.modules.m05_learning_materials.service._require_mutable",
                new=AsyncMock(return_value=pkg),
            ),
            patch.object(
                PackageItemRepository, "dedup_hash_exists", new=AsyncMock(return_value=False)
            ),
            patch.object(PackageItemRepository, "bulk_create", new=bulk_create_mock),
            patch(
                "app.modules.m05_learning_materials.service.LearningPackageRepository"
                ".update_item_count",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m05_learning_materials.service._upload_note_to_s3",
                new=AsyncMock(return_value="vidya-assets/test/faculty_notes/pkg/uuid-note.txt"),
            ),
        ):
            result = await LearningPackageService.ingest_faculty_note(
                package_id=pkg.id,
                file_bytes=txt_bytes,
                filename="lecture_notes.txt",
                content_type="text/plain",
                title="Lecture Notes Week 1",
                added_by=uuid.uuid4(),
                tenant_slug="test-uni",
                db=mock_db,
            )

            # Access call_args inside the with block while mock is active
            call_args = bulk_create_mock.call_args
            item_dict = call_args.args[1][0]

        assert result is item
        assert item_dict["source_type"].value == "FACULTY_NOTE"
        assert item_dict["faculty_recommended"] is True
        assert item_dict["title"] == "Lecture Notes Week 1"
        assert "extracted_text" in item_dict["metadata"]
        assert "Neural Networks" in item_dict["metadata"]["extracted_text"]

    @pytest.mark.asyncio
    async def test_duplicate_title_raises(self):
        from app.modules.m05_learning_materials.service import (
            LearningPackageService, PackageServiceError
        )
        from app.modules.m05_learning_materials.repository import PackageItemRepository

        mock_db = AsyncMock()
        pkg = _make_pkg()
        txt_bytes = b"Some real content here for testing."

        with (
            patch(
                "app.modules.m05_learning_materials.service._require_mutable",
                new=AsyncMock(return_value=pkg),
            ),
            patch.object(
                PackageItemRepository, "dedup_hash_exists", new=AsyncMock(return_value=True)
            ),
            patch(
                "app.modules.m05_learning_materials.service._upload_note_to_s3",
                new=AsyncMock(return_value="key"),
            ),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.ingest_faculty_note(
                    package_id=pkg.id,
                    file_bytes=txt_bytes,
                    filename="existing_note.txt",
                    content_type="text/plain",
                    title="Existing Note",
                    added_by=uuid.uuid4(),
                    tenant_slug="test-uni",
                    db=mock_db,
                )
        assert exc_info.value.code == "DUPLICATE_ITEM"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_s3_failure_does_not_block_item_creation(self):
        """S3 upload failure is logged and swallowed; item is still created."""
        from app.modules.m05_learning_materials.service import LearningPackageService
        from app.modules.m05_learning_materials.repository import PackageItemRepository

        mock_db = AsyncMock()
        pkg = _make_pkg()
        item = _make_item()
        txt_bytes = b"Valid content that should be indexed even if S3 fails."
        bulk_create_mock = AsyncMock(return_value=[item])

        with (
            patch(
                "app.modules.m05_learning_materials.service._require_mutable",
                new=AsyncMock(return_value=pkg),
            ),
            patch.object(
                PackageItemRepository, "dedup_hash_exists", new=AsyncMock(return_value=False)
            ),
            patch.object(PackageItemRepository, "bulk_create", new=bulk_create_mock),
            patch(
                "app.modules.m05_learning_materials.service.LearningPackageRepository"
                ".update_item_count",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m05_learning_materials.service._upload_note_to_s3",
                new=AsyncMock(side_effect=Exception("S3 connection refused")),
            ),
        ):
            result = await LearningPackageService.ingest_faculty_note(
                package_id=pkg.id,
                file_bytes=txt_bytes,
                filename="note.txt",
                content_type="text/plain",
                title=None,
                added_by=uuid.uuid4(),
                tenant_slug="test-uni",
                db=mock_db,
            )
            bulk_call = bulk_create_mock.call_args.args[1][0]

        assert result is item
        # metadata should NOT have storage_key when S3 failed
        assert "storage_key" not in bulk_call["metadata"]


# ---------------------------------------------------------------------------
# Router RBAC — POST /{package_id}/notes
# ---------------------------------------------------------------------------

class TestNoteUploadRouter:
    """HTTP-level smoke tests. Uses real auth, mocks LearningPackageService."""

    @pytest.mark.asyncio
    async def test_student_gets_403(
        self,
        async_client,
        test_tenant_a,
    ):
        """Students cannot upload faculty notes (RBAC: _WRITE = ADMIN + FACULTY)."""
        from tests.conftest import SCHEMA_A, SLUG_A, _insert_tenant_user, make_tenant_headers
        student = await _insert_tenant_user(
            SCHEMA_A, f"student_note_{uuid.uuid4().hex[:6]}@test.com",
            "Student1234!", "STUDENT", "Student Note",
        )
        student_full = {**student, "tenant_id": test_tenant_a["id"], "schema_name": SCHEMA_A, "slug": SLUG_A}
        headers = make_tenant_headers(student_full)
        pkg_id = uuid.uuid4()
        resp = await async_client.post(
            f"/learning-packages/{pkg_id}/notes",
            headers=headers,
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_faculty_uploads_successfully(
        self,
        async_client,
        admin_user_a,
    ):
        """Faculty / Admin can upload a note and receive the created PackageItem."""
        from tests.conftest import make_tenant_headers
        from app.modules.m05_learning_materials.models import MaterialSourceType
        from types import SimpleNamespace

        pkg_id = uuid.uuid4()
        item_id = uuid.uuid4()
        added_by_id = uuid.uuid4()

        fake_orm = SimpleNamespace(
            id=item_id,
            package_id=pkg_id,
            source_type=MaterialSourceType.FACULTY_NOTE,
            title="My Lecture Notes",
            url=None,
            content_hash=None,
            metadata_={"word_count": 5, "extracted_text": "hello world"},
            relevance_score=None,
            faculty_recommended=True,
            added_by_user_id=added_by_id,
            display_order=0,
            qdrant_indexed=False,
            created_at="2026-05-29T10:00:00+00:00",
            updated_at=None,
        )

        headers = make_tenant_headers(admin_user_a)
        note_content = b"Week 1 lecture notes on machine learning basics."

        with patch(
            "app.modules.m05_learning_materials.router.LearningPackageService"
            ".ingest_faculty_note",
            new=AsyncMock(return_value=fake_orm),
        ):
            resp = await async_client.post(
                f"/learning-packages/{pkg_id}/notes",
                headers=headers,
                files={"file": ("lecture_notes.txt", note_content, "text/plain")},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["source_type"] == "FACULTY_NOTE"
        assert data["faculty_recommended"] is True

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, async_client):
        pkg_id = uuid.uuid4()
        resp = await async_client.post(
            f"/learning-packages/{pkg_id}/notes",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 401
