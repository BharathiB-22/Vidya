"""
Smoke tests for M05 LearningPackageService (STEP-11).

Coverage:
  dispatch_curation       — happy path + 409 on CURATING
  dispatch_rag_indexing   — happy path + 409 on non-READY
  get_package             — delegates to repository
  list_packages           — pagination + status filter
  add_faculty_item        — happy path + dedup 409
  remove_item             — happy path + 404 on missing item
  toggle_faculty_recommendation — happy path
  ask_question            — happy path + NOT_INDEXED 409
  on_syllabus_version_bump — delegates to repository
  get_job_status          — delegates to TaskJobPublicRepository
  _content_hash           — deterministic SHA-256
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.modules.m05_learning_materials.models import PackageStatus, MaterialSourceType
from app.modules.m05_learning_materials.schemas import (
    CurationJobResponse,
    FacultyAddItemRequest,
    ItemMetadata,
)
from app.modules.m05_learning_materials.service import (
    LearningPackageService,
    PackageServiceError,
    _content_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_package(
    status: PackageStatus = PackageStatus.READY,
    item_count: int = 3,
    qdrant_indexed: bool = True,
) -> MagicMock:
    pkg = MagicMock()
    pkg.id            = uuid4()
    pkg.syllabus_id   = uuid4()
    pkg.unit_number   = 1
    pkg.version       = 1
    pkg.status        = status
    pkg.item_count    = item_count
    pkg.qdrant_indexed = qdrant_indexed
    return pkg


def _mock_item(package_id: UUID | None = None) -> MagicMock:
    item = MagicMock()
    item.id         = uuid4()
    item.package_id = package_id or uuid4()
    return item


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit  = AsyncMock()
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# _content_hash (pure function)
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_deterministic(self):
        h1 = _content_hash("  Hello World  ", "https://EXAMPLE.COM/path")
        h2 = _content_hash("  Hello World  ", "https://EXAMPLE.COM/path")
        assert h1 == h2

    def test_normalises_url_and_title(self):
        h = _content_hash("title", "https://Example.Com")
        expected = hashlib.sha256(b"https://example.com|title").hexdigest()
        assert h == expected

    def test_none_url_uses_empty_string(self):
        h = _content_hash("title", None)
        expected = hashlib.sha256(b"|title").hexdigest()
        assert h == expected

    def test_both_empty_returns_none(self):
        assert _content_hash("", None) is None
        assert _content_hash("  ", "") is None


# ---------------------------------------------------------------------------
# dispatch_curation
# ---------------------------------------------------------------------------

class TestDispatchCuration:
    @pytest.mark.asyncio
    async def test_happy_path_queues_task(self):
        pkg = _mock_package(status=PackageStatus.PENDING)
        job_id = uuid4()
        db = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_syllabus_unit",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.create",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository"
                ".TaskJobPublicRepository.create",
                new=AsyncMock(return_value=job_id),
            ),
            patch(
                "app.workers.heavy.curate_learning_package"
                ".curate_learning_package.delay"
            ) as mock_delay,
            patch(
                "app.core.audit_log.service.AuditService.log",
                new=AsyncMock(),
            ),
        ):
            result = await LearningPackageService.dispatch_curation(
                syllabus_id=uuid4(),
                unit_number=1,
                created_by=uuid4(),
                tenant_id=uuid4(),
                tenant_schema="t_test",
                db=db,
            )

        assert isinstance(result, CurationJobResponse)
        assert result.job_id == job_id
        assert result.package_id == pkg.id
        assert result.status == "queued"
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_when_already_curating(self):
        existing = _mock_package(status=PackageStatus.CURATING)
        db = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_syllabus_unit",
            new=AsyncMock(return_value=existing),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.dispatch_curation(
                    syllabus_id=uuid4(),
                    unit_number=1,
                    created_by=uuid4(),
                    tenant_id=uuid4(),
                    tenant_schema="t_test",
                    db=db,
                )

        err = exc_info.value
        assert err.code == "ALREADY_CURATING"
        assert err.status_code == 409


# ---------------------------------------------------------------------------
# dispatch_rag_indexing
# ---------------------------------------------------------------------------

class TestDispatchRagIndexing:
    @pytest.mark.asyncio
    async def test_happy_path_queues_task(self):
        pkg = _mock_package(status=PackageStatus.READY)
        job_id = uuid4()
        db = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository"
                ".TaskJobPublicRepository.create",
                new=AsyncMock(return_value=job_id),
            ),
            patch(
                "app.workers.heavy.index_package_rag"
                ".index_package_rag.delay"
            ) as mock_delay,
        ):
            result = await LearningPackageService.dispatch_rag_indexing(
                package_id=pkg.id,
                tenant_id=uuid4(),
                tenant_schema="t_test",
                db=db,
            )

        assert result == str(job_id)
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_non_ready_package(self):
        pkg = _mock_package(status=PackageStatus.CURATING)
        db = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.dispatch_rag_indexing(
                    package_id=pkg.id,
                    tenant_id=uuid4(),
                    tenant_schema="t_test",
                    db=db,
                )

        assert exc_info.value.code == "PACKAGE_NOT_READY"
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# get_package
# ---------------------------------------------------------------------------

class TestGetPackage:
    @pytest.mark.asyncio
    async def test_returns_package(self):
        pkg = _mock_package()
        db = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            result = await LearningPackageService.get_package(pkg.id, db=db)

        assert result is pkg

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self):
        db = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            result = await LearningPackageService.get_package(uuid4(), db=db)

        assert result is None


# ---------------------------------------------------------------------------
# list_packages
# ---------------------------------------------------------------------------

class TestListPackages:
    @pytest.mark.asyncio
    async def test_returns_total_and_items(self):
        pkgs = [_mock_package(), _mock_package()]
        db = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.count_by_syllabus",
                new=AsyncMock(return_value=2),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.list_by_syllabus",
                new=AsyncMock(return_value=pkgs),
            ),
        ):
            total, items = await LearningPackageService.list_packages(
                syllabus_id=uuid4(),
                db=db,
            )

        assert total == 2
        assert items is pkgs

    @pytest.mark.asyncio
    async def test_pagination_offset(self):
        db = _mock_db()
        list_mock = AsyncMock(return_value=[])
        count_mock = AsyncMock(return_value=0)

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.count_by_syllabus",
                new=count_mock,
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.list_by_syllabus",
                new=list_mock,
            ),
        ):
            await LearningPackageService.list_packages(
                syllabus_id=uuid4(),
                page=3,
                page_size=20,
                db=db,
            )

        call_kwargs = list_mock.call_args.kwargs
        assert call_kwargs["offset"] == 40
        assert call_kwargs["limit"] == 20


# ---------------------------------------------------------------------------
# add_faculty_item
# ---------------------------------------------------------------------------

class TestAddFacultyItem:
    def _make_payload(self, title: str = "Great Resource", url: str | None = "https://example.com") -> FacultyAddItemRequest:
        return FacultyAddItemRequest(
            source_type=MaterialSourceType.FACULTY_NOTE,
            title=title,
            url=url,
            metadata=ItemMetadata(),
        )

    @pytest.mark.asyncio
    async def test_happy_path_creates_item(self):
        pkg  = _mock_package(status=PackageStatus.READY, item_count=2)
        item = _mock_item(package_id=pkg.id)
        db   = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.dedup_hash_exists",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.bulk_create",
                new=AsyncMock(return_value=[item]),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.update_item_count",
                new=AsyncMock(),
            ),
        ):
            result = await LearningPackageService.add_faculty_item(
                package_id=pkg.id,
                payload=self._make_payload(),
                added_by=uuid4(),
                db=db,
            )

        assert result is item

    @pytest.mark.asyncio
    async def test_rejects_duplicate_item(self):
        pkg = _mock_package(status=PackageStatus.READY)
        db  = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.dedup_hash_exists",
                new=AsyncMock(return_value=True),
            ),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.add_faculty_item(
                    package_id=pkg.id,
                    payload=self._make_payload(),
                    added_by=uuid4(),
                    db=db,
                )

        assert exc_info.value.code == "DUPLICATE_ITEM"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rejects_curating_package(self):
        # _require_mutable allows PENDING+READY but blocks CURATING (AI race) + OUTDATED.
        pkg = _mock_package(status=PackageStatus.CURATING)
        db  = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.add_faculty_item(
                    package_id=pkg.id,
                    payload=self._make_payload(),
                    added_by=uuid4(),
                    db=db,
                )

        assert exc_info.value.code == "PACKAGE_CURATING"


# ---------------------------------------------------------------------------
# remove_item
# ---------------------------------------------------------------------------

class TestRemoveItem:
    @pytest.mark.asyncio
    async def test_happy_path_deletes_and_decrements(self):
        pkg  = _mock_package(status=PackageStatus.READY, item_count=3)
        item = _mock_item(package_id=pkg.id)
        db   = _mock_db()

        count_mock = AsyncMock()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.get_by_id",
                new=AsyncMock(return_value=item),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.update_item_count",
                new=count_mock,
            ),
        ):
            await LearningPackageService.remove_item(
                package_id=pkg.id,
                item_id=item.id,
                db=db,
            )

        count_mock.assert_called_once_with(pkg.id, 2, db=db)

    @pytest.mark.asyncio
    async def test_raises_404_for_wrong_package(self):
        pkg     = _mock_package(status=PackageStatus.READY)
        item    = _mock_item(package_id=uuid4())  # different package
        db      = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.get_by_id",
                new=AsyncMock(return_value=item),
            ),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.remove_item(
                    package_id=pkg.id,
                    item_id=item.id,
                    db=db,
                )

        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# toggle_faculty_recommendation
# ---------------------------------------------------------------------------

class TestToggleFacultyRecommendation:
    @pytest.mark.asyncio
    async def test_happy_path_returns_updated_item(self):
        pkg     = _mock_package(status=PackageStatus.READY)
        item    = _mock_item(package_id=pkg.id)
        updated = _mock_item(package_id=pkg.id)
        db      = _mock_db()

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.get_by_id",
                new=AsyncMock(return_value=item),
            ),
            patch(
                "app.modules.m05_learning_materials.repository"
                ".PackageItemRepository.set_faculty_recommended",
                new=AsyncMock(return_value=updated),
            ),
        ):
            result = await LearningPackageService.toggle_faculty_recommendation(
                package_id=pkg.id,
                item_id=item.id,
                value=True,
                db=db,
            )

        assert result is updated


# ---------------------------------------------------------------------------
# ask_question
# ---------------------------------------------------------------------------

class TestAskQuestion:
    @pytest.mark.asyncio
    async def test_delegates_to_rag_service(self):
        pkg = _mock_package(status=PackageStatus.READY, qdrant_indexed=True)
        db  = _mock_db()
        rag_response = {
            "session_id": uuid4(),
            "message_id": uuid4(),
            "answer": "42",
            "sources": [],
            "model_used": "gemini-flash",
        }

        with (
            patch(
                "app.modules.m05_learning_materials.repository"
                ".LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.rag_service"
                ".ask_package_question",
                new=AsyncMock(return_value=rag_response),
            ),
        ):
            result = await LearningPackageService.ask_question(
                package_id=pkg.id,
                student_user_id=uuid4(),
                question="What is this?",
                tenant_schema="t_test",
                session_id=None,
                db=db,
            )

        assert result["answer"] == "42"

    @pytest.mark.asyncio
    async def test_raises_not_indexed_when_not_indexed(self):
        pkg = _mock_package(status=PackageStatus.READY, qdrant_indexed=False)
        db  = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.ask_question(
                    package_id=pkg.id,
                    student_user_id=uuid4(),
                    question="What is this?",
                    tenant_schema="t_test",
                    session_id=None,
                    db=db,
                )

        assert exc_info.value.code == "NOT_INDEXED"
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_raises_not_ready_for_non_ready_package(self):
        pkg = _mock_package(status=PackageStatus.PENDING)
        db  = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await LearningPackageService.ask_question(
                    package_id=pkg.id,
                    student_user_id=uuid4(),
                    question="What is this?",
                    tenant_schema="t_test",
                    session_id=None,
                    db=db,
                )

        assert exc_info.value.code == "PACKAGE_NOT_READY"


# ---------------------------------------------------------------------------
# on_syllabus_version_bump
# ---------------------------------------------------------------------------

class TestOnSyllabusVersionBump:
    @pytest.mark.asyncio
    async def test_returns_count_and_commits(self):
        db = _mock_db()

        with patch(
            "app.modules.m05_learning_materials.repository"
            ".LearningPackageRepository.mark_outdated_by_syllabus",
            new=AsyncMock(return_value=4),
        ):
            count = await LearningPackageService.on_syllabus_version_bump(
                syllabus_id=uuid4(),
                db=db,
            )

        assert count == 4
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------

class TestGetJobStatus:
    @pytest.mark.asyncio
    async def test_delegates_to_task_job_repository(self):
        db      = _mock_db()
        job_id  = uuid4()
        tenant  = uuid4()
        payload = {"status": "SUCCESS"}

        with patch(
            "app.modules.m02_syllabus.repository"
            ".TaskJobPublicRepository.get_by_id",
            new=AsyncMock(return_value=payload),
        ):
            result = await LearningPackageService.get_job_status(
                job_id=job_id,
                tenant_id=tenant,
                db=db,
            )

        assert result == payload
