"""
Smoke tests for the Qdrant RAG indexing pipeline — STEP-09.

Covers:
  - Pure helpers: _build_index_text, _chunk_text, _chunk_point_id
  - Integration path: mocked Qdrant, mocked repositories, mocked embedder
  - Payload structure (tenant_schema, package_id, item_id, source_type)
  - Vector upserts called with correct collection name
  - Chunk ordering is deterministic
  - Per-item qdrant_indexed flags set correctly
  - Package qdrant_indexed flag set after all items
  - Per-item failure tolerance (one bad item, others complete)
  - Catastrophic Qdrant failure fails task cleanly
  - Tenant-safe payload metadata on every point

No real Qdrant, database, or network calls.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.heavy.index_package_rag import (
    _build_index_text,
    _chunk_point_id,
    _chunk_text,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

TENANT_SCHEMA = "tenant_acme"
PACKAGE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    *,
    item_id: uuid.UUID | None = None,
    source_type: str = "ARXIV",
    title: str = "Test Paper",
    url: str = "https://example.com/paper",
    metadata: dict | None = None,
) -> MagicMock:
    item = MagicMock()
    item.id = item_id or uuid.uuid4()
    item.source_type = MagicMock()
    item.source_type.value = source_type
    item.title = title
    item.url = url
    item.metadata_ = metadata if metadata is not None else {}
    return item


def _make_mock_qdrant() -> MagicMock:
    qdrant = AsyncMock()
    collections_result = MagicMock()
    collections_result.collections = []
    qdrant.get_collections = AsyncMock(return_value=collections_result)
    qdrant.create_collection = AsyncMock()
    qdrant.upsert = AsyncMock()
    return qdrant


def _make_session_ctx() -> tuple[MagicMock, AsyncMock]:
    """Return (AsyncSession class mock, session instance mock)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    cls = MagicMock()
    cls.return_value.__aenter__ = AsyncMock(return_value=session)
    cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cls, session


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------

class TestBuildIndexText:
    def test_title_only(self):
        item = _make_item(title="Introduction to ML", metadata={})
        assert _build_index_text(item) == "Introduction to ML"

    def test_title_plus_abstract(self):
        item = _make_item(
            title="Deep Learning",
            metadata={"abstract_snippet": "Neural network survey."},
        )
        result = _build_index_text(item)
        assert "Deep Learning" in result
        assert "Neural network survey." in result

    def test_empty_abstract_falls_back_to_title(self):
        item = _make_item(title="Lecture 5", metadata={"abstract_snippet": ""})
        assert _build_index_text(item) == "Lecture 5"

    def test_none_metadata_(self):
        item = _make_item(title="Unit 3")
        item.metadata_ = None
        assert _build_index_text(item) == "Unit 3"


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        chunks = _chunk_text("hello world", 512, 128)
        assert chunks == ["hello world"]

    def test_long_text_produces_multiple_chunks(self):
        # 512 tokens * 4 chars = 2048 chars per chunk; 3000 > 2048
        long_text = "A" * 3000
        chunks = _chunk_text(long_text, 512, 128)
        assert len(chunks) > 1

    def test_overlap_is_preserved(self):
        chunk_tokens = 10   # 40 chars
        overlap_tokens = 5  # 20 chars
        text = "X" * 100
        chunks = _chunk_text(text, chunk_tokens, overlap_tokens)
        assert len(chunks) > 1
        # end of chunk[0] == start of chunk[1] (overlap region)
        assert chunks[0][-20:] == chunks[1][:20]

    def test_ordering_is_deterministic(self):
        text = "Word " * 500
        assert _chunk_text(text, 20, 5) == _chunk_text(text, 20, 5)

    def test_exactly_one_chunk_length_is_single(self):
        text = "B" * (512 * 4)
        chunks = _chunk_text(text, 512, 128)
        assert len(chunks) == 1

    def test_stride_clamp_prevents_infinite_loop(self):
        # overlap >= chunk_size; stride must be clamped to 1
        chunks = _chunk_text("ABCDE", chunk_tokens=1, overlap_tokens=2)
        assert len(chunks) >= 1  # does not hang; produces something


class TestChunkPointId:
    def test_deterministic(self):
        item_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert _chunk_point_id(item_id, 0) == _chunk_point_id(item_id, 0)

    def test_different_chunk_index_gives_different_id(self):
        item_id = uuid.uuid4()
        assert _chunk_point_id(item_id, 0) != _chunk_point_id(item_id, 1)

    def test_different_item_id_gives_different_id(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        assert _chunk_point_id(a, 0) != _chunk_point_id(b, 0)

    def test_returns_uuid(self):
        pid = _chunk_point_id(uuid.uuid4(), 0)
        assert isinstance(pid, uuid.UUID)


# ---------------------------------------------------------------------------
# Integration-style tests (mocked Qdrant + repos + embedder)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_indexing_indexes_single_item():
    item = _make_item(title="Lecture 1", metadata={"abstract_snippet": "Intro."})
    qdrant = _make_mock_qdrant()
    session_cls, session = _make_session_ctx()
    fake_vector = [0.1] * 768

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=item),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[fake_vector]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        result = await _run_indexing(
            package_id=PACKAGE_ID,
            tenant_id=TENANT_ID,
            tenant_schema=TENANT_SCHEMA,
        )

    assert result["indexed_count"] == 1
    assert result["failed_count"] == 0
    assert result["total_vectors"] == 1
    qdrant.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_payload_contains_required_tenant_fields():
    """Every Qdrant point payload must carry tenant_schema, package_id, item_id, source_type."""
    item = _make_item(
        item_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        source_type="YOUTUBE",
        title="ML Lecture",
    )
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()
    fake_vector = [0.2] * 768

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=item),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[fake_vector]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    upsert_call = qdrant.upsert.call_args
    points = upsert_call.kwargs["points"]
    assert len(points) == 1
    payload = points[0].payload

    assert payload["tenant_schema"] == TENANT_SCHEMA
    assert payload["package_id"] == str(PACKAGE_ID)
    assert payload["item_id"] == str(item.id)
    assert payload["source_type"] == "YOUTUBE"


@pytest.mark.asyncio
async def test_chunk_ordering_in_payload():
    """Multiple chunks must be upserted in deterministic index order."""
    long_text = "Sentence. " * 300  # ~3000 chars > 2048 (512 tokens)
    item = _make_item(title=long_text)
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()

    # Simulate embed_texts returning one vector per chunk
    async def fake_embed(texts, **kw):
        return [[float(i)] * 768 for i in range(len(texts))]

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=item),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=fake_embed),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    upsert_call = qdrant.upsert.call_args
    points = upsert_call.kwargs["points"]
    assert len(points) > 1, "Expected multiple chunks for long text"

    chunk_indices = [p.payload["chunk_index"] for p in points]
    assert chunk_indices == sorted(chunk_indices), "Chunks must be in ascending order"
    assert chunk_indices[0] == 0


@pytest.mark.asyncio
async def test_per_item_qdrant_indexed_flag_set():
    """set_qdrant_indexed must be called once per successfully indexed item."""
    items = [
        _make_item(item_id=uuid.uuid4(), title=f"Item {i}") for i in range(3)
    ]
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()
    mock_set_item_indexed = AsyncMock(return_value=None)

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=items),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=mock_set_item_indexed,
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[[0.1] * 768]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        result = await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    assert result["indexed_count"] == 3
    assert mock_set_item_indexed.call_count == 3


@pytest.mark.asyncio
async def test_package_indexed_flag_set_after_all_items():
    """LearningPackageRepository.set_qdrant_indexed must be called exactly once."""
    item = _make_item()
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()
    mock_set_pkg_indexed = AsyncMock(return_value=None)

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=mock_set_pkg_indexed,
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[[0.1] * 768]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    mock_set_pkg_indexed.assert_called_once()
    called_package_id = mock_set_pkg_indexed.call_args.args[0]
    assert called_package_id == PACKAGE_ID


@pytest.mark.asyncio
async def test_per_item_failure_does_not_abort_package():
    """One item that fails embedding must not prevent other items from being indexed."""
    good_item = _make_item(item_id=uuid.uuid4(), title="Good Item")
    bad_item = _make_item(item_id=uuid.uuid4(), title="Bad Item")

    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()
    mock_set_item_indexed = AsyncMock(return_value=None)
    mock_set_pkg_indexed = AsyncMock(return_value=None)

    call_count = 0

    async def embed_side_effect(texts, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Embedding provider error")
        return [[0.1] * 768 for _ in texts]

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[bad_item, good_item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=mock_set_item_indexed,
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=mock_set_pkg_indexed,
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=embed_side_effect,
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        result = await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    assert result["indexed_count"] == 1
    assert result["failed_count"] == 1
    # Package-level flag still set even with partial failures
    mock_set_pkg_indexed.assert_called_once()
    # Only the good item's per-item flag should be set
    assert mock_set_item_indexed.call_count == 1


@pytest.mark.asyncio
async def test_catastrophic_qdrant_failure_fails_task_cleanly():
    """If collection setup raises, task fails and audit log is written."""
    qdrant = AsyncMock()
    qdrant.get_collections = AsyncMock(side_effect=RuntimeError("Qdrant unreachable"))
    session_cls, _ = _make_session_ctx()
    mock_audit = AsyncMock()

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch("app.core.audit_log.service.AuditService.log", new=mock_audit),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        with pytest.raises(RuntimeError):
            await _run_indexing(
                package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
            )

    # Failure audit event must be logged
    audit_calls = [str(c.args[0]) for c in mock_audit.call_args_list]
    assert any("RAG_INDEXING_FAILED" in ev for ev in audit_calls)


@pytest.mark.asyncio
async def test_empty_package_completes_with_zero_vectors():
    """Package with no items completes cleanly; package flag is still set."""
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()
    mock_set_pkg_indexed = AsyncMock(return_value=None)

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=mock_set_pkg_indexed,
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        result = await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    assert result["indexed_count"] == 0
    assert result["total_vectors"] == 0
    mock_set_pkg_indexed.assert_called_once()
    qdrant.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_tenant_safe_payload_metadata_on_every_point():
    """All points upserted must carry tenant_schema and package_id; no cross-tenant leakage."""
    items = [_make_item(item_id=uuid.uuid4(), title=f"Item {i}") for i in range(2)]
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=items),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[[0.1] * 768]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    assert qdrant.upsert.call_count == 2
    for upsert_call in qdrant.upsert.call_args_list:
        points = upsert_call.kwargs["points"]
        for point in points:
            assert point.payload["tenant_schema"] == TENANT_SCHEMA
            assert point.payload["package_id"] == str(PACKAGE_ID)
            assert "item_id" in point.payload
            assert "source_type" in point.payload


@pytest.mark.asyncio
async def test_qdrant_upsert_uses_correct_collection_name():
    item = _make_item()
    qdrant = _make_mock_qdrant()
    session_cls, _ = _make_session_ctx()

    with (
        patch("app.workers.heavy.index_package_rag._get_async_engine"),
        patch("app.workers.heavy.index_package_rag._get_qdrant_client", return_value=qdrant),
        patch("sqlalchemy.ext.asyncio.AsyncSession", session_cls),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.list_by_package",
            new=AsyncMock(return_value=[item]),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.PackageItemRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_qdrant_indexed",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=[[0.1] * 768]),
        ),
        patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
    ):
        from app.workers.heavy.index_package_rag import _run_indexing
        await _run_indexing(
            package_id=PACKAGE_ID, tenant_id=TENANT_ID, tenant_schema=TENANT_SCHEMA
        )

    upsert_call = qdrant.upsert.call_args
    assert upsert_call.kwargs["collection_name"] == "m05_rag"
