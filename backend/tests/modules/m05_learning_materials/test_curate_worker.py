"""
Unit tests for M05 curate_learning_package worker — partial adapter failure (H-17/12).

These tests mock all I/O (DB, adapters, embedder) to verify the three-case branching
logic without requiring a running database.

Cases under test:
  A — Some adapters succeed: rank AI items, preserve & resequence faculty items.
  B — All adapters fail, faculty items exist: skip ranking, mark READY with warning.
  C — All adapters fail, no faculty items: raise RuntimeError (hard fail).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pkg(status="PENDING", top_n=5):
    pkg = MagicMock()
    pkg.id = uuid.uuid4()
    pkg.top_n = top_n

    class _Status:
        PENDING  = "PENDING"
        CURATING = "CURATING"
        READY    = "READY"
        OUTDATED = "OUTDATED"

    pkg.status = _Status.PENDING
    return pkg, _Status


def _make_unit():
    unit = MagicMock()
    unit.title = "Intro to AI"
    unit.topics = [{"title": "Machine Learning"}, {"title": "Neural Networks"}]
    return unit


def _make_raw_item(title="Test Video", url="https://example.com/v1"):
    item = MagicMock()
    item.source_type = "YOUTUBE"
    item.title = title
    item.url = url
    item.metadata = {}
    return item


def _make_faculty_item(item_id=None, display_order=0):
    item = MagicMock()
    item.id = item_id or uuid.uuid4()
    item.display_order = display_order
    return item


def _make_mock_session():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__  = AsyncMock(return_value=False)
    mock_session.execute    = AsyncMock()
    mock_session.flush      = AsyncMock()
    mock_session.commit     = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# Repository method existence tests (import-level, no DB needed)
# ---------------------------------------------------------------------------

def test_package_item_repo_has_list_faculty_added():
    from app.modules.m05_learning_materials.repository import PackageItemRepository
    assert callable(getattr(PackageItemRepository, "list_faculty_added", None))


def test_package_item_repo_has_delete_ai_items():
    from app.modules.m05_learning_materials.repository import PackageItemRepository
    assert callable(getattr(PackageItemRepository, "delete_ai_items", None))


def test_package_item_repo_has_update_display_order():
    from app.modules.m05_learning_materials.repository import PackageItemRepository
    assert callable(getattr(PackageItemRepository, "update_display_order", None))


# ---------------------------------------------------------------------------
# Worker: Case C — all adapters fail, no faculty items → hard fail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_c_raises_when_no_items_and_no_faculty():
    """Case C: RuntimeError when all adapters fail AND no faculty items exist."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg()
    unit         = _make_unit()
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    with (
        patch("app.workers.heavy.curate_learning_package._get_async_engine",
              return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("sqlalchemy.text", return_value=MagicMock()),
        patch("app.config.settings") as mock_settings,
        patch("app.core.audit_log.models.AuditEventType"),
        patch("app.core.audit_log.service.AuditService"),
        patch("app.modules.m02_syllabus.repository.SyllabusUnitRepository") as mock_unit_repo,
        patch("app.modules.m05_learning_materials.embedder.score_items"),
        patch("app.modules.m05_learning_materials.embedder.EmbedderError", Exception),
        patch("app.modules.m05_learning_materials.models.PackageStatus", _Status),
        patch("app.modules.m05_learning_materials.repository.LearningPackageRepository") as mock_lp,
        patch("app.modules.m05_learning_materials.repository.PackageItemRepository") as mock_items,
        patch("app.modules.m05_learning_materials.source_adapters.YouTubeAdapter") as YT,
        patch("app.modules.m05_learning_materials.source_adapters.ArxivAdapter") as AX,
        patch("app.modules.m05_learning_materials.source_adapters.NptelAdapter") as NP,
        patch("app.modules.m05_learning_materials.source_adapters.MitOcwAdapter") as MI,
        patch("app.modules.m05_learning_materials.source_adapters.SourceAdapterError",
              SourceAdapterError),
    ):
        mock_settings.M05_TOP_N_PER_UNIT = 5
        mock_lp.get_by_id     = AsyncMock(return_value=pkg)
        mock_lp.set_curating  = AsyncMock(return_value=pkg)
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)

        for adapter_cls in [YT, AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("provider down"))
            adapter_cls.return_value = inst

        mock_items.list_faculty_added = AsyncMock(return_value=[])

        from app.workers.heavy.curate_learning_package import _run_curation

        with pytest.raises(RuntimeError, match="All source adapters failed"):
            await _run_curation(
                package_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                tenant_schema="dsu",
                syllabus_id=uuid.uuid4(),
                unit_number=1,
                top_n=5,
            )


# ---------------------------------------------------------------------------
# Worker: Case B — all adapters fail, faculty items exist → READY with warning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_b_marks_ready_with_warning_when_faculty_items_exist():
    """Case B: package marked READY when all adapters fail but faculty items exist."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg()
    unit         = _make_unit()
    fac_item     = _make_faculty_item()
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    with (
        patch("app.workers.heavy.curate_learning_package._get_async_engine",
              return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("sqlalchemy.text", return_value=MagicMock()),
        patch("app.config.settings") as mock_settings,
        patch("app.core.audit_log.models.AuditEventType"),
        patch("app.core.audit_log.service.AuditService") as mock_audit,
        patch("app.modules.m02_syllabus.repository.SyllabusUnitRepository") as mock_unit_repo,
        patch("app.modules.m05_learning_materials.embedder.score_items"),
        patch("app.modules.m05_learning_materials.embedder.EmbedderError", Exception),
        patch("app.modules.m05_learning_materials.models.PackageStatus", _Status),
        patch("app.modules.m05_learning_materials.repository.LearningPackageRepository") as mock_lp,
        patch("app.modules.m05_learning_materials.repository.PackageItemRepository") as mock_items,
        patch("app.modules.m05_learning_materials.source_adapters.YouTubeAdapter") as YT,
        patch("app.modules.m05_learning_materials.source_adapters.ArxivAdapter") as AX,
        patch("app.modules.m05_learning_materials.source_adapters.NptelAdapter") as NP,
        patch("app.modules.m05_learning_materials.source_adapters.MitOcwAdapter") as MI,
        patch("app.modules.m05_learning_materials.source_adapters.SourceAdapterError",
              SourceAdapterError),
    ):
        mock_settings.M05_TOP_N_PER_UNIT = 5
        mock_lp.get_by_id     = AsyncMock(return_value=pkg)
        mock_lp.set_curating  = AsyncMock(return_value=pkg)
        mock_lp.set_ready     = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit.log = AsyncMock()

        for adapter_cls in [YT, AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("provider down"))
            adapter_cls.return_value = inst

        mock_items.list_faculty_added = AsyncMock(return_value=[fac_item])

        from app.workers.heavy.curate_learning_package import _run_curation

        result = await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    assert result["items_created"] == 0
    assert result["faculty_items_kept"] == 1
    assert "warning" in result
    assert "faculty-added resources only" in result["warning"]

    mock_lp.set_ready.assert_called_once()
    assert mock_lp.set_ready.call_args.kwargs.get("item_count") == 1


# ---------------------------------------------------------------------------
# Worker: Case A — adapters return items, faculty items preserved + resequenced
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_a_preserves_faculty_items_and_resequences():
    """Case A: AI items ranked, faculty items preserved and resequenced after AI items."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg()
    unit         = _make_unit()
    fac_item     = _make_faculty_item()
    raw_item     = _make_raw_item()
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    created_ai_item = MagicMock()

    with (
        patch("app.workers.heavy.curate_learning_package._get_async_engine",
              return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("sqlalchemy.text", return_value=MagicMock()),
        patch("app.config.settings") as mock_settings,
        patch("app.core.audit_log.models.AuditEventType"),
        patch("app.core.audit_log.service.AuditService") as mock_audit,
        patch("app.modules.m02_syllabus.repository.SyllabusUnitRepository") as mock_unit_repo,
        patch("app.modules.m05_learning_materials.embedder.score_items") as mock_score,
        patch("app.modules.m05_learning_materials.embedder.EmbedderError", Exception),
        patch("app.modules.m05_learning_materials.models.PackageStatus", _Status),
        patch("app.modules.m05_learning_materials.repository.LearningPackageRepository") as mock_lp,
        patch("app.modules.m05_learning_materials.repository.PackageItemRepository") as mock_items,
        patch("app.modules.m05_learning_materials.source_adapters.YouTubeAdapter") as YT,
        patch("app.modules.m05_learning_materials.source_adapters.ArxivAdapter") as AX,
        patch("app.modules.m05_learning_materials.source_adapters.NptelAdapter") as NP,
        patch("app.modules.m05_learning_materials.source_adapters.MitOcwAdapter") as MI,
        patch("app.modules.m05_learning_materials.source_adapters.SourceAdapterError",
              SourceAdapterError),
    ):
        mock_settings.M05_TOP_N_PER_UNIT = 5
        mock_lp.get_by_id     = AsyncMock(return_value=pkg)
        mock_lp.set_curating  = AsyncMock(return_value=pkg)
        mock_lp.set_ready     = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit.log = AsyncMock()

        # YouTube succeeds, others fail
        yt_inst = AsyncMock()
        yt_inst.search = AsyncMock(return_value=[raw_item])
        YT.return_value = yt_inst
        for adapter_cls in [AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("provider down"))
            adapter_cls.return_value = inst

        mock_score.return_value = [(raw_item, 0.9)]

        mock_items.list_faculty_added   = AsyncMock(return_value=[fac_item])
        mock_items.delete_ai_items      = AsyncMock(return_value=0)
        mock_items.bulk_create          = AsyncMock(return_value=[created_ai_item])
        mock_items.update_display_order = AsyncMock()

        from app.workers.heavy.curate_learning_package import _run_curation

        result = await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    assert result["items_created"] == 1
    assert result["faculty_items_kept"] == 1
    assert result.get("warning") is None

    # Faculty item resequenced to display_order = 1 (after 1 AI item)
    # update_display_order(fi.id, ai_count + idx, db=session) → positional[1] = 1
    mock_items.update_display_order.assert_called_once()
    assert mock_items.update_display_order.call_args.args[1] == 1

    # set_ready with total = 1 AI + 1 faculty = 2
    mock_lp.set_ready.assert_called_once()
    assert mock_lp.set_ready.call_args.kwargs.get("item_count") == 2

    # delete_ai_items called (not delete_all_for_package)
    mock_items.delete_ai_items.assert_called_once()
