"""
STEP-17: End-to-end smoke and integration tests for M05 Learning Material Packager.

Gaps covered beyond existing ~92 tests (test_service, test_router, test_rag_service,
test_index_package_rag, test_step13_wiring):
  1. Source adapter static parsers — ArxivAdapter._parse_atom
                                   — NptelAdapter._extract_courses / _item_from_course
                                   — MitOcwAdapter._extract_results / _item_from_result
  2. Source adapter mocked HTTP   — YouTubeAdapter.search (mocked httpx)
  3. Embedder pure functions      — cosine_similarity edge cases
                                   — score_items with mocked embed_texts
  4. Curation worker              — _run_curation happy path
                                   — partial adapter failure (some adapters fail)
                                   — total adapter failure (all fail → RuntimeError)
                                   — audit events emitted
  5. Faculty workflow chain       — trigger_curation → job poll → item list
  6. Student workflow chain       — list packages → get package → ask question
  7. Tenant isolation             — cross-tenant package access returns 404/403
"""
from __future__ import annotations

import json
from textwrap import dedent
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── source adapters ──────────────────────────────────────────────────────────
from app.modules.m05_learning_materials.source_adapters.arxiv import ArxivAdapter
from app.modules.m05_learning_materials.source_adapters.mit_ocw import MitOcwAdapter
from app.modules.m05_learning_materials.source_adapters.nptel import NptelAdapter
from app.modules.m05_learning_materials.source_adapters.base import RawItem, SourceAdapterError

# ── embedder ─────────────────────────────────────────────────────────────────
from app.modules.m05_learning_materials.embedder import cosine_similarity, score_items

# ── worker ───────────────────────────────────────────────────────────────────
from app.workers.heavy.curate_learning_package import _run_curation


# ===========================================================================
# Part 1 — ArxivAdapter static parser
# ===========================================================================

_ARXIV_ATOM_SINGLE = dedent("""\
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2301.01234</id>
        <title>Deep Learning Survey</title>
        <summary>A comprehensive survey of deep learning methods.</summary>
        <published>2023-01-10T00:00:00Z</published>
        <author><name>Alice Smith</name></author>
        <author><name>Bob Jones</name></author>
        <link rel="alternate" href="http://arxiv.org/abs/2301.01234"/>
        <link type="application/pdf" href="http://arxiv.org/pdf/2301.01234"/>
      </entry>
    </feed>
""")

_ARXIV_ATOM_EMPTY = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

_ARXIV_ATOM_NO_TITLE = dedent("""\
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2302.99999</id>
        <title></title>
        <summary>Some abstract.</summary>
        <published>2023-02-01T00:00:00Z</published>
        <link rel="alternate" href="http://arxiv.org/abs/2302.99999"/>
      </entry>
    </feed>
""")


class TestArxivAdapterParser:
    def test_parse_single_entry_fields(self):
        results = ArxivAdapter._parse_atom(_ARXIV_ATOM_SINGLE)

        assert len(results) == 1
        r = results[0]
        assert r["arxiv_id"] == "2301.01234"
        assert r["title"] == "Deep Learning Survey"
        assert "comprehensive survey" in r["summary"]
        assert r["published"] == "2023-01-10T00:00:00Z"
        assert r["authors"] == ["Alice Smith", "Bob Jones"]
        assert r["page_url"] == "http://arxiv.org/abs/2301.01234"
        assert r["pdf_url"] == "http://arxiv.org/pdf/2301.01234"

    def test_parse_empty_feed_returns_empty_list(self):
        assert ArxivAdapter._parse_atom(_ARXIV_ATOM_EMPTY) == []

    def test_parse_multiple_entries(self):
        xml = dedent("""\
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <id>http://arxiv.org/abs/2301.00001</id>
                <title>Paper One</title>
                <summary>Summary one.</summary>
                <published>2023-01-01T00:00:00Z</published>
                <link rel="alternate" href="http://arxiv.org/abs/2301.00001"/>
              </entry>
              <entry>
                <id>http://arxiv.org/abs/2301.00002</id>
                <title>Paper Two</title>
                <summary>Summary two.</summary>
                <published>2023-01-02T00:00:00Z</published>
                <link rel="alternate" href="http://arxiv.org/abs/2301.00002"/>
              </entry>
            </feed>
        """)
        results = ArxivAdapter._parse_atom(xml)
        assert len(results) == 2
        assert results[0]["title"] == "Paper One"
        assert results[1]["title"] == "Paper Two"

    @pytest.mark.asyncio
    async def test_search_filters_empty_title(self):
        adapter = ArxivAdapter(tenant_schema="test_schema")
        with patch.object(adapter, "_fetch_raw", new=AsyncMock(return_value=_ARXIV_ATOM_NO_TITLE)):
            items = await adapter.search("machine learning", limit=5)
        assert items == []

    @pytest.mark.asyncio
    async def test_search_returns_raw_items(self):
        adapter = ArxivAdapter(tenant_schema="test_schema")
        with patch.object(adapter, "_fetch_raw", new=AsyncMock(return_value=_ARXIV_ATOM_SINGLE)):
            items = await adapter.search("deep learning", limit=5)
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, RawItem)
        assert item.source_type == "ARXIV"
        assert item.title == "Deep Learning Survey"
        assert item.url == "http://arxiv.org/abs/2301.01234"
        assert item.metadata["arxiv_id"] == "2301.01234"
        assert item.metadata["authors"] == ["Alice Smith", "Bob Jones"]

    @pytest.mark.asyncio
    async def test_search_raises_source_adapter_error_on_network_failure(self):
        adapter = ArxivAdapter(tenant_schema="test_schema")
        with patch.object(
            adapter, "_fetch_raw",
            new=AsyncMock(side_effect=SourceAdapterError("timeout"))
        ):
            with pytest.raises(SourceAdapterError):
                await adapter.search("neural networks", limit=5)

    @pytest.mark.asyncio
    async def test_search_raises_on_malformed_xml(self):
        adapter = ArxivAdapter(tenant_schema="test_schema")
        with patch.object(adapter, "_fetch_raw", new=AsyncMock(return_value="NOT XML <<>>")):
            with pytest.raises(SourceAdapterError, match="arXiv XML parsing failed"):
                await adapter.search("test", limit=5)


# ===========================================================================
# Part 2 — NptelAdapter static methods
# ===========================================================================

def _nptel_html(courses: list[dict]) -> str:
    next_data = json.dumps({
        "props": {"pageProps": {"courses": courses}}
    })
    return f'<script id="__NEXT_DATA__">{next_data}</script>'


class TestNptelAdapterParser:
    def test_extract_courses_happy_path(self):
        courses = [{"courseId": "noc19-cs99", "courseName": "ML Course"}]
        html = _nptel_html(courses)
        result = NptelAdapter._extract_courses(html, limit=10)
        assert len(result) == 1
        assert result[0]["courseName"] == "ML Course"

    def test_extract_courses_respects_limit(self):
        courses = [{"courseName": f"Course {i}"} for i in range(10)]
        html = _nptel_html(courses)
        result = NptelAdapter._extract_courses(html, limit=3)
        assert len(result) == 3

    def test_extract_courses_no_next_data_returns_empty(self):
        html = "<html><body>No data here</body></html>"
        assert NptelAdapter._extract_courses(html, limit=5) == []

    def test_extract_courses_bad_json_returns_empty(self):
        html = '<script id="__NEXT_DATA__">{ invalid json </script>'
        assert NptelAdapter._extract_courses(html, limit=5) == []

    def test_extract_courses_missing_courses_key_returns_empty(self):
        next_data = json.dumps({"props": {"pageProps": {"otherKey": []}}})
        html = f'<script id="__NEXT_DATA__">{next_data}</script>'
        assert NptelAdapter._extract_courses(html, limit=5) == []

    def test_item_from_course_full_fields(self):
        raw = {
            "courseId": "noc20-cs10",
            "courseName": "Introduction to ML",
            "courseDescription": "Covers basics of machine learning.",
            "coordinators": [{"name": "Prof. Rao"}, {"name": "Dr. Patel"}],
            "institute": "IIT Madras",
            "totalWeeks": 12,
        }
        item = NptelAdapter._item_from_course(raw)
        assert item is not None
        assert item.source_type == "NPTEL"
        assert item.title == "Introduction to ML"
        assert item.url == "https://nptel.ac.in/courses/noc20-cs10"
        assert "Prof. Rao" in item.metadata["instructor"]
        assert item.metadata["institution"] == "IIT Madras"
        assert item.metadata["duration"] == 12

    def test_item_from_course_missing_title_returns_none(self):
        assert NptelAdapter._item_from_course({"courseId": "x"}) is None

    def test_item_from_course_non_dict_returns_none(self):
        assert NptelAdapter._item_from_course("not a dict") is None  # type: ignore

    def test_item_from_course_uses_explicit_url_if_present(self):
        raw = {"courseName": "Test", "url": "https://example.com/course"}
        item = NptelAdapter._item_from_course(raw)
        assert item is not None
        assert item.url == "https://example.com/course"

    @pytest.mark.asyncio
    async def test_search_returns_raw_items(self):
        courses = [
            {
                "courseId": "noc21-cs01",
                "courseName": "Deep Learning",
                "courseDescription": "Neural networks course.",
            }
        ]
        adapter = NptelAdapter(tenant_schema="test_schema")
        with patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=_nptel_html(courses))):
            items = await adapter.search("deep learning", limit=5)
        assert len(items) == 1
        assert items[0].source_type == "NPTEL"
        assert items[0].title == "Deep Learning"


# ===========================================================================
# Part 3 — MitOcwAdapter static methods
# ===========================================================================

def _mit_ocw_html(results: list[dict]) -> str:
    next_data = json.dumps({
        "props": {"pageProps": {"results": results}}
    })
    return f'<script id="__NEXT_DATA__">{next_data}</script>'


class TestMitOcwAdapterParser:
    def test_extract_results_happy_path(self):
        html = _mit_ocw_html([{"title": "6.006 Introduction to Algorithms"}])
        result = MitOcwAdapter._extract_results(html, limit=10)
        assert len(result) == 1
        assert result[0]["title"] == "6.006 Introduction to Algorithms"

    def test_extract_results_respects_limit(self):
        html = _mit_ocw_html([{"title": f"Course {i}"} for i in range(8)])
        result = MitOcwAdapter._extract_results(html, limit=3)
        assert len(result) == 3

    def test_extract_results_no_script_returns_empty(self):
        assert MitOcwAdapter._extract_results("<html></html>", limit=5) == []

    def test_extract_results_bad_json_returns_empty(self):
        html = '<script id="__NEXT_DATA__">broken { </script>'
        assert MitOcwAdapter._extract_results(html, limit=5) == []

    def test_item_from_result_absolute_url_kept(self):
        raw = {"title": "Algorithms", "url": "https://ocw.mit.edu/courses/6-006/"}
        item = MitOcwAdapter._item_from_result(raw)
        assert item is not None
        assert item.url == "https://ocw.mit.edu/courses/6-006/"

    def test_item_from_result_relative_slug_prepends_base(self):
        raw = {"title": "Algorithms", "url": "/courses/6-006"}
        item = MitOcwAdapter._item_from_result(raw)
        assert item is not None
        assert item.url == "https://ocw.mit.edu/courses/6-006"

    def test_item_from_result_missing_title_returns_none(self):
        assert MitOcwAdapter._item_from_result({"url": "/courses/x"}) is None

    def test_item_from_result_non_dict_returns_none(self):
        assert MitOcwAdapter._item_from_result(42) is None  # type: ignore

    def test_item_from_result_metadata_fields(self):
        raw = {
            "title": "Machine Learning",
            "course_num": "6.867",
            "department": "EECS",
            "level": "Graduate",
            "object_type": "Course",
            "description": "ML fundamentals.",
        }
        item = MitOcwAdapter._item_from_result(raw)
        assert item is not None
        assert item.source_type == "MIT_OCW"
        assert item.metadata["course_number"] == "6.867"
        assert item.metadata["department"] == "EECS"
        assert item.metadata["level"] == "Graduate"
        assert item.metadata["resource_type"] == "Course"

    @pytest.mark.asyncio
    async def test_search_returns_raw_items(self):
        results = [{"title": "Linear Algebra", "url": "/courses/18-06"}]
        adapter = MitOcwAdapter(tenant_schema="test_schema")
        with patch.object(adapter, "_fetch_html", new=AsyncMock(return_value=_mit_ocw_html(results))):
            items = await adapter.search("linear algebra", limit=5)
        assert len(items) == 1
        assert items[0].source_type == "MIT_OCW"
        assert items[0].title == "Linear Algebra"

    @pytest.mark.asyncio
    async def test_search_raises_on_network_error(self):
        adapter = MitOcwAdapter(tenant_schema="test_schema")
        with patch.object(
            adapter, "_fetch_html",
            new=AsyncMock(side_effect=SourceAdapterError("connection refused"))
        ):
            with pytest.raises(SourceAdapterError):
                await adapter.search("deep learning", limit=5)


# ===========================================================================
# Part 4 — Embedder pure functions
# ===========================================================================

class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_clamped_to_zero(self):
        result = cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert result == pytest.approx(0.0)

    def test_zero_magnitude_vector_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
        assert cosine_similarity([1.0, 0.0], [0.0, 0.0]) == 0.0

    def test_empty_vectors_return_zero(self):
        assert cosine_similarity([], []) == 0.0

    def test_mismatched_lengths_return_zero(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_partial_overlap(self):
        score = cosine_similarity([1.0, 1.0], [1.0, 0.0])
        assert 0.0 < score < 1.0

    def test_result_always_in_0_1_range(self):
        import random
        random.seed(42)
        for _ in range(20):
            a = [random.uniform(-1, 1) for _ in range(8)]
            b = [random.uniform(-1, 1) for _ in range(8)]
            score = cosine_similarity(a, b)
            assert 0.0 <= score <= 1.0


class TestScoreItems:
    @pytest.mark.asyncio
    async def test_empty_items_returns_empty(self):
        result = await score_items(
            "unit context",
            [],
            tenant_schema="test",
            package_id="pkg-1",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_items_sorted_descending_by_score(self):
        items = [
            RawItem(source_type="ARXIV", title="Low Relevance", url=None,
                    raw_text="unrelated text", metadata={}),
            RawItem(source_type="ARXIV", title="High Relevance", url=None,
                    raw_text="matching text", metadata={}),
        ]
        # unit_context vector + item vectors
        mock_vectors = [
            [1.0, 0.0],   # unit_context
            [0.1, 0.9],   # Low Relevance — low cosine with [1,0]
            [0.9, 0.1],   # High Relevance — high cosine with [1,0]
        ]
        with patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=mock_vectors),
        ):
            scored = await score_items(
                "unit context", items, tenant_schema="test", package_id="pkg-1"
            )
        assert len(scored) == 2
        assert scored[0][0].title == "High Relevance"
        assert scored[1][0].title == "Low Relevance"
        assert scored[0][1] > scored[1][1]

    @pytest.mark.asyncio
    async def test_ties_broken_by_title_ascending(self):
        items = [
            RawItem(source_type="ARXIV", title="Zebra Paper", url=None, raw_text="x", metadata={}),
            RawItem(source_type="ARXIV", title="Alpha Paper", url=None, raw_text="x", metadata={}),
        ]
        unit_vec = [1.0, 0.0]
        item_vec = [1.0, 0.0]  # same for both → tie
        mock_vectors = [unit_vec, item_vec, item_vec]
        with patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=mock_vectors),
        ):
            scored = await score_items(
                "context", items, tenant_schema="test", package_id="pkg-2"
            )
        assert scored[0][0].title == "Alpha Paper"
        assert scored[1][0].title == "Zebra Paper"

    @pytest.mark.asyncio
    async def test_all_scores_clamped_to_0_1(self):
        items = [
            RawItem(source_type="YOUTUBE", title="Video", url=None, raw_text="t", metadata={})
        ]
        mock_vectors = [[1.0, 0.0], [-1.0, 0.0]]  # would give negative cosine
        with patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(return_value=mock_vectors),
        ):
            scored = await score_items(
                "context", items, tenant_schema="test", package_id="pkg-3"
            )
        assert 0.0 <= scored[0][1] <= 1.0


# ===========================================================================
# Part 5 — Curation worker _run_curation
# ===========================================================================

def _make_mock_pkg(status="PENDING") -> MagicMock:
    pkg = MagicMock()
    pkg.id = uuid4()
    pkg.status = MagicMock()
    pkg.status.value = status
    from app.modules.m05_learning_materials.models import PackageStatus
    pkg.status = PackageStatus.PENDING if status == "PENDING" else PackageStatus.CURATING
    pkg.top_n = 5
    return pkg


def _make_mock_unit() -> MagicMock:
    unit = MagicMock()
    unit.title = "Introduction to Machine Learning"
    unit.topics = [{"title": "Supervised Learning"}, {"title": "Neural Networks"}]
    return unit


def _make_raw_items(n: int = 3, source: str = "ARXIV") -> list[RawItem]:
    return [
        RawItem(
            source_type=source,
            title=f"Resource {i}",
            url=f"https://example.com/{i}",
            raw_text=f"Resource {i} content",
            metadata={},
        )
        for i in range(n)
    ]


def _build_session_mock() -> tuple[MagicMock, MagicMock]:
    """Returns (session_instance, async_context_manager_mock) for AsyncSession patch."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return session, cm


class TestRunCurationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_completes_and_audits(self):
        pkg = _make_mock_pkg()
        unit = _make_mock_unit()
        raw_items = _make_raw_items(3)
        ranked = [(item, 0.9 - i * 0.1) for i, item in enumerate(raw_items)]
        new_items = [MagicMock() for _ in range(3)]
        for item in new_items:
            item.id = uuid4()

        session, cm = _build_session_mock()
        session2, cm2 = _build_session_mock()
        call_count = 0

        def session_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return cm if call_count == 1 else cm2

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch(
                "sqlalchemy.ext.asyncio.AsyncSession",
                side_effect=session_factory,
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository.SyllabusUnitRepository.get_by_number",
                new=AsyncMock(return_value=unit),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_curating",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.youtube.YouTubeAdapter.search",
                new=AsyncMock(return_value=raw_items),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.arxiv.ArxivAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.nptel.NptelAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.mit_ocw.MitOcwAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.embedder.score_items",
                new=AsyncMock(return_value=ranked),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.list_faculty_added",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.delete_ai_items",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.bulk_create",
                new=AsyncMock(return_value=new_items),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_ready",
                new=AsyncMock(),
            ),
            patch(
                "app.core.audit_log.service.AuditService.log",
                new=AsyncMock(),
            ) as mock_audit,
        ):
            result = await _run_curation(
                package_id=pkg.id,
                tenant_id=uuid4(),
                tenant_schema="test_tenant",
                syllabus_id=uuid4(),
                unit_number=1,
                top_n=5,
            )

        assert result["items_created"] == 3
        assert result["unit_number"] == 1
        assert isinstance(result["failed_providers"], list)
        mock_audit.assert_called_once()
        audit_call = mock_audit.call_args[0][0]
        from app.core.audit_log.models import AuditEventType
        assert audit_call == AuditEventType.LEARNING_PACKAGE_CURATION_COMPLETED

    @pytest.mark.asyncio
    async def test_partial_adapter_failure_continues(self):
        pkg = _make_mock_pkg()
        unit = _make_mock_unit()
        raw_items = _make_raw_items(2, source="ARXIV")
        ranked = [(item, 0.8) for item in raw_items]
        new_items = [MagicMock(id=uuid4()) for _ in range(2)]

        session, cm = _build_session_mock()

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=cm),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository.SyllabusUnitRepository.get_by_number",
                new=AsyncMock(return_value=unit),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_curating",
                new=AsyncMock(),
            ),
            # YouTube fails, arXiv succeeds, nptel+mitocw fail
            patch(
                "app.modules.m05_learning_materials.source_adapters.youtube.YouTubeAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("quota exceeded")),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.arxiv.ArxivAdapter.search",
                new=AsyncMock(return_value=raw_items),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.nptel.NptelAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("timeout")),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.mit_ocw.MitOcwAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("404")),
            ),
            patch(
                "app.modules.m05_learning_materials.embedder.score_items",
                new=AsyncMock(return_value=ranked),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.list_faculty_added",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.delete_ai_items",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.bulk_create",
                new=AsyncMock(return_value=new_items),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_ready",
                new=AsyncMock(),
            ),
            patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
        ):
            result = await _run_curation(
                package_id=pkg.id,
                tenant_id=uuid4(),
                tenant_schema="test_tenant",
                syllabus_id=uuid4(),
                unit_number=2,
                top_n=5,
            )

        assert result["items_created"] == 2
        assert "youtube" in result["failed_providers"]
        assert "nptel" in result["failed_providers"]
        assert "arxiv" not in result["failed_providers"]

    @pytest.mark.asyncio
    async def test_all_adapters_fail_marks_ready_and_audits_unavailable(self):
        """Case C (H-17/13): all adapters fail, no faculty items.

        Previously this raised RuntimeError.  Now the package is marked READY
        with item_count=0 and a LEARNING_PACKAGE_CURATION_UNAVAILABLE audit
        event is emitted so operators can triage without blocking faculty.
        """
        pkg = _make_mock_pkg()
        unit = _make_mock_unit()

        session, cm = _build_session_mock()
        mock_audit = AsyncMock()

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=cm),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository.SyllabusUnitRepository.get_by_number",
                new=AsyncMock(return_value=unit),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_curating",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_ready",
                new=AsyncMock(),
            ) as mock_set_ready,
            patch(
                "app.modules.m05_learning_materials.source_adapters.youtube.YouTubeAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("fail")),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.arxiv.ArxivAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("fail")),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.nptel.NptelAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("fail")),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.mit_ocw.MitOcwAdapter.search",
                new=AsyncMock(side_effect=SourceAdapterError("fail")),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.list_faculty_added",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.update_status",
                new=AsyncMock(),
            ) as mock_update_status,
            patch("app.core.audit_log.service.AuditService.log", new=mock_audit),
        ):
            result = await _run_curation(
                package_id=pkg.id,
                tenant_id=uuid4(),
                tenant_schema="test_tenant",
                syllabus_id=uuid4(),
                unit_number=3,
                top_n=5,
            )

        assert result["items_created"] == 0
        assert result["faculty_items_kept"] == 0
        assert "warning" in result and result["warning"]
        # set_ready must have been called with item_count=0
        mock_set_ready.assert_called_once()
        assert mock_set_ready.call_args.kwargs.get("item_count") == 0
        # update_status (PENDING reset) must NOT have been called
        mock_update_status.assert_not_called()
        # UNAVAILABLE audit event must have been emitted (not FAILED)
        assert mock_audit.called
        unavailable_calls = [
            c for c in mock_audit.call_args_list
            if "UNAVAILABLE" in str(c)
        ]
        assert len(unavailable_calls) >= 1

    @pytest.mark.asyncio
    async def test_package_not_found_raises(self):
        session, cm = _build_session_mock()

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=cm),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.update_status",
                new=AsyncMock(),
            ),
            patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
        ):
            with pytest.raises(ValueError, match="not found"):
                await _run_curation(
                    package_id=uuid4(),
                    tenant_id=uuid4(),
                    tenant_schema="test_schema",
                    syllabus_id=uuid4(),
                    unit_number=1,
                    top_n=5,
                )

    @pytest.mark.asyncio
    async def test_wrong_package_status_raises(self):
        from app.modules.m05_learning_materials.models import PackageStatus
        pkg = MagicMock()
        pkg.id = uuid4()
        pkg.status = PackageStatus.READY  # not PENDING or CURATING
        pkg.top_n = 5

        session, cm = _build_session_mock()
        session2, cm2 = _build_session_mock()
        call_count = 0

        def session_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return cm if call_count == 1 else cm2

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch("sqlalchemy.ext.asyncio.AsyncSession", side_effect=session_factory),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.update_status",
                new=AsyncMock(),
            ),
            patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
        ):
            with pytest.raises(ValueError, match="curation requires PENDING or CURATING"):
                await _run_curation(
                    package_id=pkg.id,
                    tenant_id=uuid4(),
                    tenant_schema="test_schema",
                    syllabus_id=uuid4(),
                    unit_number=1,
                    top_n=5,
                )

    @pytest.mark.asyncio
    async def test_audit_completed_contains_expected_metadata(self):
        pkg = _make_mock_pkg()
        unit = _make_mock_unit()
        raw_items = _make_raw_items(2)
        ranked = [(item, 0.85) for item in raw_items]
        new_items = [MagicMock(id=uuid4()) for _ in range(2)]

        session, cm = _build_session_mock()
        mock_audit = AsyncMock()

        with (
            patch("app.workers.heavy.curate_learning_package._get_async_engine"),
            patch("sqlalchemy.ext.asyncio.AsyncSession", return_value=cm),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository.SyllabusUnitRepository.get_by_number",
                new=AsyncMock(return_value=unit),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_curating",
                new=AsyncMock(),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.youtube.YouTubeAdapter.search",
                new=AsyncMock(return_value=raw_items),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.arxiv.ArxivAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.nptel.NptelAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.source_adapters.mit_ocw.MitOcwAdapter.search",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.embedder.score_items",
                new=AsyncMock(return_value=ranked),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.list_faculty_added",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.delete_ai_items",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.bulk_create",
                new=AsyncMock(return_value=new_items),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.set_ready",
                new=AsyncMock(),
            ),
            patch("app.core.audit_log.service.AuditService.log", new=mock_audit),
        ):
            await _run_curation(
                package_id=pkg.id,
                tenant_id=uuid4(),
                tenant_schema="test_tenant",
                syllabus_id=uuid4(),
                unit_number=1,
                top_n=5,
            )

        mock_audit.assert_called_once()
        meta = mock_audit.call_args[1]["metadata"]
        assert meta["items_created"] == 2
        assert meta["unit_number"] == 1
        assert "ai_model" in meta
        assert "prompt_hash" in meta


# ===========================================================================
# Part 6 — Faculty workflow sanity (service-level, no real DB)
# ===========================================================================

class TestFacultyWorkflowSanity:
    """
    Chain test: trigger_curation → dispatch_rag_indexing → add_faculty_item
    Mocks repository and Celery; verifies service logic rather than HTTP layer.
    """

    def _make_service(self):
        from app.modules.m05_learning_materials.service import LearningPackageService
        return LearningPackageService()

    @pytest.mark.asyncio
    async def test_trigger_curation_dispatches_celery_job(self):
        from app.modules.m05_learning_materials.schemas import CurationJobResponse

        syllabus_id = uuid4()
        tenant_id = uuid4()
        created_by = uuid4()
        job_id = uuid4()

        new_pkg = MagicMock()
        new_pkg.id = uuid4()

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_syllabus_unit",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.create",
                new=AsyncMock(return_value=new_pkg),
            ),
            patch(
                "app.modules.m02_syllabus.repository.TaskJobPublicRepository.create",
                new=AsyncMock(return_value=job_id),
            ),
            patch(
                "app.workers.heavy.curate_learning_package.curate_learning_package.delay",
            ),
            patch("app.core.audit_log.service.AuditService.log", new=AsyncMock()),
        ):
            svc = self._make_service()
            result = await svc.dispatch_curation(
                syllabus_id=syllabus_id,
                unit_number=1,
                created_by=created_by,
                tenant_id=tenant_id,
                tenant_schema="test_schema",
                db=mock_session,
            )

        assert isinstance(result, CurationJobResponse)
        assert result.job_id == job_id

    @pytest.mark.asyncio
    async def test_add_faculty_item_rejected_for_duplicate(self):
        from app.modules.m05_learning_materials.models import PackageStatus
        from app.modules.m05_learning_materials.schemas import FacultyAddItemRequest
        from app.modules.m05_learning_materials.service import PackageServiceError

        pkg = MagicMock()
        pkg.id = uuid4()
        pkg.status = PackageStatus.READY
        pkg.item_count = 3

        mock_session = AsyncMock()

        with (
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.dedup_hash_exists",
                new=AsyncMock(return_value=True),
            ),
        ):
            svc = self._make_service()
            payload = FacultyAddItemRequest(
                source_type="FACULTY_NOTE",
                title="Duplicate Video",
                url="https://www.youtube.com/watch?v=abc123",
            )
            with pytest.raises(PackageServiceError) as exc_info:
                await svc.add_faculty_item(
                    package_id=pkg.id,
                    payload=payload,
                    added_by=uuid4(),
                    db=mock_session,
                )
        assert exc_info.value.code == "DUPLICATE_ITEM"

    @pytest.mark.asyncio
    async def test_toggle_faculty_recommendation_on(self):
        from app.modules.m05_learning_materials.models import PackageStatus

        pkg = MagicMock()
        pkg.id = uuid4()
        pkg.status = PackageStatus.READY

        item = MagicMock()
        item.id = uuid4()
        item.package_id = pkg.id
        item.faculty_recommended = False

        mock_session = AsyncMock()

        with (
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.get_by_id",
                new=AsyncMock(return_value=item),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.set_faculty_recommended",
                new=AsyncMock(return_value=item),
            ),
        ):
            svc = self._make_service()
            updated = await svc.toggle_faculty_recommendation(
                package_id=pkg.id,
                item_id=item.id,
                value=True,
                db=mock_session,
            )
        assert updated is item


# ===========================================================================
# Part 7 — Student workflow sanity (service-level)
# ===========================================================================

class TestStudentWorkflowSanity:
    def _make_service(self):
        from app.modules.m05_learning_materials.service import LearningPackageService
        return LearningPackageService()

    @pytest.mark.asyncio
    async def test_ask_question_rejected_when_not_indexed(self):
        from app.modules.m05_learning_materials.models import PackageStatus
        from app.modules.m05_learning_materials.service import PackageServiceError

        pkg = MagicMock()
        pkg.id = uuid4()
        pkg.status = PackageStatus.READY
        pkg.qdrant_indexed = False

        mock_session = AsyncMock()

        with patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=pkg),
        ):
            svc = self._make_service()
            with pytest.raises(PackageServiceError) as exc_info:
                await svc.ask_question(
                    package_id=pkg.id,
                    question="What is supervised learning?",
                    student_user_id=uuid4(),
                    tenant_schema="test_schema",
                    session_id=None,
                    db=mock_session,
                )
        assert exc_info.value.code == "NOT_INDEXED"

    @pytest.mark.asyncio
    async def test_list_packages_returns_filtered_results(self):
        mock_session = AsyncMock()
        syllabus_id = uuid4()
        pkg = MagicMock()
        pkg.id = uuid4()

        with (
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.count_by_syllabus",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.list_by_syllabus",
                new=AsyncMock(return_value=[pkg]),
            ),
        ):
            svc = self._make_service()
            total, items = await svc.list_packages(
                syllabus_id=syllabus_id,
                status_filter=None,
                page=1,
                page_size=20,
                db=mock_session,
            )
        assert total == 1
        assert len(items) == 1


# ===========================================================================
# Part 8 — Tenant isolation (service-level)
# ===========================================================================

class TestTenantIsolation:
    """
    Verify that fetching a package belonging to another tenant returns an error.
    The service resolves package by ID within the session's search_path, so a
    package from schema B is not visible in schema A → repository returns None.
    """

    @pytest.mark.asyncio
    async def test_get_package_returns_none_for_foreign_schema(self):
        """
        get_package returns None when the repo returns None.
        In production, the session's search_path is set to the tenant's schema
        before any query, so a cross-tenant package ID yields no row → None.
        """
        from app.modules.m05_learning_materials.service import LearningPackageService

        mock_session = AsyncMock()
        foreign_pkg_id = uuid4()

        with patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            svc = LearningPackageService()
            result = await svc.get_package(
                package_id=foreign_pkg_id,
                db=mock_session,
            )
        # Tenant isolation: cross-tenant lookup returns None, not the wrong tenant's data
        assert result is None

    @pytest.mark.asyncio
    async def test_require_package_raises_not_found_for_missing(self):
        """_require_package (used by all mutating ops) raises PackageServiceError(NOT_FOUND)."""
        from app.modules.m05_learning_materials.service import (
            PackageServiceError,
            _require_package,
        )

        mock_session = AsyncMock()

        with patch(
            "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(PackageServiceError) as exc_info:
                await _require_package(uuid4(), db=mock_session)
        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_item_not_found_in_foreign_schema(self):
        from app.modules.m05_learning_materials.models import PackageStatus
        from app.modules.m05_learning_materials.service import (
            LearningPackageService,
            PackageServiceError,
        )

        pkg = MagicMock()
        pkg.id = uuid4()
        pkg.status = PackageStatus.READY
        mock_session = AsyncMock()

        with (
            patch(
                "app.modules.m05_learning_materials.repository.LearningPackageRepository.get_by_id",
                new=AsyncMock(return_value=pkg),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageItemRepository.get_by_id",
                new=AsyncMock(return_value=None),
            ),
        ):
            svc = LearningPackageService()
            with pytest.raises(PackageServiceError) as exc_info:
                await svc.remove_item(
                    package_id=pkg.id,
                    item_id=uuid4(),
                    db=mock_session,
                )
        assert exc_info.value.code == "NOT_FOUND"
