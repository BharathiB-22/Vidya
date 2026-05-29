"""
Unit tests for M05 curate_learning_package worker — partial adapter failure (H-17/12).

These tests mock all I/O (DB, adapters, embedder) to verify the three-case branching
logic without requiring a running database.

Cases under test:
  A — Some adapters succeed: rank AI items, preserve & resequence faculty items.
  B — All adapters fail, faculty items exist: skip ranking, mark READY with warning.
  C — All adapters fail, no faculty items: raise RuntimeError (hard fail).

QA-fix tests (2026-05-29):
  _build_search_queries — per-provider query builder
  relevance threshold   — items below M05_MIN_RELEVANCE_SCORE rejected
  per-provider queries  — adapters receive provider-specific queries, not raw unit_context
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
# Worker: Case C — all adapters fail, no faculty items
# ---------------------------------------------------------------------------
# Behaviour changed in H-17/13: Case C no longer hard-fails.  The package is
# marked READY with item_count=0 so faculty can add resources later.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_c_marks_ready_with_zero_items_no_raise():
    """Case C: no RuntimeError; package becomes READY with item_count=0."""
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
        mock_lp.get_by_id    = AsyncMock(return_value=pkg)
        mock_lp.set_curating = AsyncMock(return_value=pkg)
        mock_lp.set_ready    = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit.log = AsyncMock()

        for adapter_cls in [YT, AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("provider down"))
            adapter_cls.return_value = inst

        mock_items.list_faculty_added = AsyncMock(return_value=[])

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
    assert result["faculty_items_kept"] == 0
    assert "warning" in result and result["warning"]
    mock_lp.set_ready.assert_called_once()
    assert mock_lp.set_ready.call_args.kwargs.get("item_count") == 0
    # PENDING reset path must NOT have been called
    mock_lp.update_status.assert_not_called()


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
        mock_settings.M05_TOP_N_PER_UNIT      = 5
        mock_settings.M05_MIN_RELEVANCE_SCORE = 0.0  # pass all items (this test is about resequencing)
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


# ---------------------------------------------------------------------------
# Worker: Case C — audit event + provider warning + no PENDING reset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_case_c_emits_curation_unavailable_audit():
    """Case C: LEARNING_PACKAGE_CURATION_UNAVAILABLE audit event is emitted."""
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
        patch("app.core.audit_log.models.AuditEventType") as mock_audit_evt,
        patch("app.core.audit_log.service.AuditService") as mock_audit_svc,
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
        mock_lp.get_by_id    = AsyncMock(return_value=pkg)
        mock_lp.set_curating = AsyncMock(return_value=pkg)
        mock_lp.set_ready    = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit_svc.log = AsyncMock()

        for adapter_cls in [YT, AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("down"))
            adapter_cls.return_value = inst

        mock_items.list_faculty_added = AsyncMock(return_value=[])

        from app.workers.heavy.curate_learning_package import _run_curation
        await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    mock_audit_svc.log.assert_called_once()
    called_event = mock_audit_svc.log.call_args.args[0]
    assert called_event == mock_audit_evt.LEARNING_PACKAGE_CURATION_UNAVAILABLE


@pytest.mark.asyncio
async def test_case_c_warning_mentions_unavailable_providers():
    """Case C: warning string references the providers that failed/returned nothing.

    Realistic scenario: youtube + arxiv raise SourceAdapterError;
    nptel + mit_ocw return [] silently.  Only the two raisers appear in
    failed_providers; the warning still contains useful context.
    """
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
        patch("app.core.audit_log.service.AuditService") as mock_audit_svc,
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
        mock_lp.get_by_id    = AsyncMock(return_value=pkg)
        mock_lp.set_curating = AsyncMock(return_value=pkg)
        mock_lp.set_ready    = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit_svc.log = AsyncMock()

        yt_inst = AsyncMock(); yt_inst.search = AsyncMock(side_effect=SourceAdapterError("quota"))
        ax_inst = AsyncMock(); ax_inst.search = AsyncMock(side_effect=SourceAdapterError("timeout"))
        np_inst = AsyncMock(); np_inst.search = AsyncMock(return_value=[])
        mi_inst = AsyncMock(); mi_inst.search = AsyncMock(return_value=[])
        YT.return_value = yt_inst
        AX.return_value = ax_inst
        NP.return_value = np_inst
        MI.return_value = mi_inst

        mock_items.list_faculty_added = AsyncMock(return_value=[])

        from app.workers.heavy.curate_learning_package import _run_curation
        result = await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    assert result["failed_providers"] == ["youtube", "arxiv"]
    assert "unavailable" in result["warning"].lower()
    assert result["items_created"] == 0


@pytest.mark.asyncio
async def test_case_c_does_not_reset_to_pending():
    """Case C: set_ready is called, update_status(PENDING) is NOT called."""
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
        patch("app.core.audit_log.service.AuditService") as mock_audit_svc,
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
        mock_lp.get_by_id    = AsyncMock(return_value=pkg)
        mock_lp.set_curating = AsyncMock(return_value=pkg)
        mock_lp.set_ready    = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit_svc.log = AsyncMock()

        for adapter_cls in [YT, AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("down"))
            adapter_cls.return_value = inst

        mock_items.list_faculty_added = AsyncMock(return_value=[])

        from app.workers.heavy.curate_learning_package import _run_curation
        await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    mock_lp.set_ready.assert_called_once()
    mock_lp.update_status.assert_not_called()


# ===========================================================================
# _build_search_queries — unit tests (no I/O, no DB)
# ===========================================================================

class TestBuildSearchQueries:
    """Verify that the per-provider query builder produces correct output."""

    def _q(self, unit_title, topics=None):
        from app.workers.heavy.curate_learning_package import _build_search_queries
        return _build_search_queries(unit_title, topics or [])

    def test_returns_all_four_providers(self):
        q = self._q("Introduction to AI")
        assert set(q.keys()) == {"youtube", "arxiv", "nptel", "mit_ocw"}

    def test_youtube_contains_lecture_tutorial(self):
        q = self._q("Introduction to Artificial Intelligence")
        assert "lecture" in q["youtube"].lower() or "tutorial" in q["youtube"].lower()

    def test_youtube_contains_unit_title(self):
        q = self._q("Machine Learning Fundamentals")
        assert "Machine Learning Fundamentals" in q["youtube"]

    def test_arxiv_uses_ti_prefix(self):
        q = self._q("Neural Networks")
        assert q["arxiv"].startswith('ti:"')

    def test_arxiv_includes_cs_category_filter(self):
        q = self._q("Neural Networks")
        assert "cat:cs.AI" in q["arxiv"]
        assert "cat:cs.LG" in q["arxiv"]

    def test_arxiv_does_not_use_all_prefix(self):
        """The old bug was all:{unit_context}; new query must NOT use all:."""
        q = self._q("Introduction to Artificial Intelligence",
                    ["History of AI", "Intelligent Agents", "Search Algorithms"])
        assert not q["arxiv"].startswith("all:")

    def test_arxiv_does_not_contain_topics_label(self):
        """The string 'Topics:' must not appear in any query (it confused arXiv)."""
        q = self._q("Intro to AI", ["History", "Search"])
        for provider, query in q.items():
            assert "Topics:" not in query, f"{provider} query still has 'Topics:'"

    def test_nptel_contains_unit_title(self):
        q = self._q("Database Management Systems", ["SQL", "Normalization"])
        assert "Database Management Systems" in q["nptel"]

    def test_nptel_includes_topic_supplement(self):
        q = self._q("Data Structures", ["Arrays", "Linked Lists", "Trees", "Graphs"])
        # Up to first 3 topics included
        assert "Arrays" in q["nptel"]
        assert "Linked Lists" in q["nptel"]
        assert "Trees" in q["nptel"]
        # 4th topic must not be in NPTEL query (limit is 3)
        assert "Graphs" not in q["nptel"]

    def test_mit_ocw_uses_clean_title_only(self):
        q = self._q("Algorithms and Complexity", ["P vs NP", "Sorting"])
        assert q["mit_ocw"] == "Algorithms and Complexity"

    def test_empty_topics_still_works(self):
        q = self._q("Compiler Design", [])
        assert "Compiler Design" in q["youtube"]
        assert "Compiler Design" in q["arxiv"]
        assert q["mit_ocw"] == "Compiler Design"

    def test_title_with_leading_whitespace_is_stripped(self):
        q = self._q("  Operating Systems  ", [])
        assert q["mit_ocw"] == "Operating Systems"
        assert not q["youtube"].startswith(" ")

    def test_ai_fundamentals_arxiv_no_gravitational_waves(self):
        """Regression: AI Fundamentals must not produce a query that hits physics papers."""
        q = self._q(
            "Introduction to Artificial Intelligence",
            ["History of AI", "Intelligent Agents", "Search Algorithms",
             "Knowledge Representation", "Machine Learning"],
        )
        arxiv_q = q["arxiv"]
        # Must be category-filtered to CS
        assert "cat:cs.AI" in arxiv_q
        # Must not be an open all: query that matches physics
        assert "all:" not in arxiv_q
        # No astrophysics-attracting keywords
        assert "gravitational" not in arxiv_q.lower()
        assert "LIGO" not in arxiv_q


# ===========================================================================
# Relevance threshold filtering — Case A variant tests
# ===========================================================================

def _make_raw_item_scored(title, url, score):
    """Helper: (RawItem-like mock, score) pair for ranked list."""
    item = MagicMock()
    item.source_type = "YOUTUBE"
    item.title = title
    item.url = url
    item.metadata = {}
    return (item, score)


@pytest.mark.asyncio
async def test_relevance_threshold_rejects_low_score_items():
    """Items below M05_MIN_RELEVANCE_SCORE are rejected from the final package."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg()
    unit         = _make_unit()
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    high_item = _make_raw_item("AI Tutorial High", "https://yt.com/high")
    low_item  = _make_raw_item("Gravitational Waves", "https://arxiv.org/gw")
    # ranked list: high item scores 0.85, low item scores 0.30
    ranked_pairs = [
        (high_item, 0.85),
        (low_item,  0.30),
    ]

    captured_bulk_items = []

    async def _fake_bulk_create(package_id, items_data, *, db):
        captured_bulk_items.extend(items_data)
        return [MagicMock() for _ in items_data]

    with (
        patch("app.workers.heavy.curate_learning_package._get_async_engine",
              return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("sqlalchemy.text", return_value=MagicMock()),
        patch("app.config.settings") as mock_settings,
        patch("app.core.audit_log.models.AuditEventType"),
        patch("app.core.audit_log.service.AuditService") as mock_audit,
        patch("app.core.notifications.models.NotificationType"),
        patch("app.core.notifications.service.NotificationService") as mock_notif,
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
        mock_settings.M05_TOP_N_PER_UNIT  = 5
        mock_settings.M05_MIN_RELEVANCE_SCORE = 0.5
        mock_lp.get_by_id     = AsyncMock(return_value=pkg)
        mock_lp.set_curating  = AsyncMock(return_value=pkg)
        mock_lp.set_ready     = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit.log  = AsyncMock()
        mock_notif.send = AsyncMock()

        yt_inst = AsyncMock()
        yt_inst.search = AsyncMock(return_value=[high_item, low_item])
        YT.return_value = yt_inst
        for cls in [AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("down"))
            cls.return_value = inst

        mock_score.return_value = ranked_pairs

        mock_items.list_faculty_added   = AsyncMock(return_value=[])
        mock_items.delete_ai_items      = AsyncMock(return_value=0)
        mock_items.bulk_create          = AsyncMock(side_effect=_fake_bulk_create)
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

    # Only the high-score item should have been sent to bulk_create
    assert result["items_created"] == 1
    assert len(captured_bulk_items) == 1
    assert captured_bulk_items[0]["title"] == "AI Tutorial High"
    assert captured_bulk_items[0]["relevance_score"] == 0.85


@pytest.mark.asyncio
async def test_relevance_threshold_fallback_when_nothing_passes():
    """If NO items pass the threshold, fall back to all ranked items (graceful degradation)."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg(top_n=5)
    unit         = _make_unit()
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    # All items score below threshold of 0.9
    ranked_pairs = [
        (_make_raw_item("Item A", "https://yt.com/a"), 0.40),
        (_make_raw_item("Item B", "https://yt.com/b"), 0.30),
        (_make_raw_item("Item C", "https://yt.com/c"), 0.20),
    ]

    all_items_raw = [pair[0] for pair in ranked_pairs]
    captured_bulk_items = []

    async def _fake_bulk_create(package_id, items_data, *, db):
        captured_bulk_items.extend(items_data)
        return [MagicMock() for _ in items_data]

    with (
        patch("app.workers.heavy.curate_learning_package._get_async_engine",
              return_value=mock_engine),
        patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=mock_session),
        patch("sqlalchemy.text", return_value=MagicMock()),
        patch("app.config.settings") as mock_settings,
        patch("app.core.audit_log.models.AuditEventType"),
        patch("app.core.audit_log.service.AuditService") as mock_audit,
        patch("app.core.notifications.models.NotificationType"),
        patch("app.core.notifications.service.NotificationService") as mock_notif,
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
        mock_settings.M05_TOP_N_PER_UNIT      = 5
        mock_settings.M05_MIN_RELEVANCE_SCORE = 0.9  # very strict — nothing passes
        mock_lp.get_by_id     = AsyncMock(return_value=pkg)
        mock_lp.set_curating  = AsyncMock(return_value=pkg)
        mock_lp.set_ready     = AsyncMock()
        mock_lp.update_status = AsyncMock()
        mock_unit_repo.get_by_number = AsyncMock(return_value=unit)
        mock_audit.log  = AsyncMock()
        mock_notif.send = AsyncMock()

        yt_inst = AsyncMock()
        yt_inst.search = AsyncMock(return_value=all_items_raw)
        YT.return_value = yt_inst
        for cls in [AX, NP, MI]:
            inst = AsyncMock()
            inst.search = AsyncMock(side_effect=SourceAdapterError("down"))
            cls.return_value = inst

        mock_score.return_value = ranked_pairs

        mock_items.list_faculty_added   = AsyncMock(return_value=[])
        mock_items.delete_ai_items      = AsyncMock(return_value=0)
        mock_items.bulk_create          = AsyncMock(side_effect=_fake_bulk_create)
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

    # Fallback: all 3 ranked items used because nothing passed the 0.9 threshold
    assert result["items_created"] == 3


# ===========================================================================
# Per-provider query routing — adapters receive purpose-built queries
# ===========================================================================

@pytest.mark.asyncio
async def test_adapters_receive_per_provider_queries_not_unit_context():
    """Each adapter is called with its provider-specific query, not the raw unit_context."""
    from app.modules.m05_learning_materials.source_adapters import SourceAdapterError

    pkg, _Status = _make_pkg()
    unit         = _make_unit()  # title="Intro to AI", topics=[ML, NN]
    mock_session = _make_mock_session()
    mock_engine  = MagicMock()

    captured_queries: dict[str, str] = {}

    def _make_adapter(name):
        inst = AsyncMock()
        async def _search(query, limit):
            captured_queries[name] = query
            raise SourceAdapterError("intentional stop")
        inst.search = _search
        return inst

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

        YT.return_value = _make_adapter("youtube")
        AX.return_value = _make_adapter("arxiv")
        NP.return_value = _make_adapter("nptel")
        MI.return_value = _make_adapter("mit_ocw")
        mock_items.list_faculty_added = AsyncMock(return_value=[])

        from app.workers.heavy.curate_learning_package import _run_curation
        await _run_curation(
            package_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            tenant_schema="dsu",
            syllabus_id=uuid.uuid4(),
            unit_number=1,
            top_n=5,
        )

    # YouTube must include "lecture" or "tutorial"
    assert "lecture" in captured_queries["youtube"].lower() or \
           "tutorial" in captured_queries["youtube"].lower(), \
           f"YouTube query bad: {captured_queries['youtube']!r}"

    # arXiv must use Boolean ti: syntax with CS category filter
    assert captured_queries["arxiv"].startswith('ti:"'), \
           f"arXiv query must start with ti:\": {captured_queries['arxiv']!r}"
    assert "cat:cs.AI" in captured_queries["arxiv"], \
           f"arXiv query must filter CS: {captured_queries['arxiv']!r}"

    # No adapter should receive the raw unit_context string with "Topics:" in it
    unit_context_marker = "Topics:"
    for provider, query in captured_queries.items():
        assert unit_context_marker not in query, \
               f"{provider} received raw unit_context (contains 'Topics:'): {query!r}"
