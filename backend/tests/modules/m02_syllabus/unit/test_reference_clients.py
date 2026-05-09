"""
Unit tests for M02 CrossRefClient and OpenLibraryClient.
All HTTP calls are patched at the _get_with_retry level so no network
access is required. Tests verify response parsing, field normalisation,
retry behaviour, and error propagation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.modules.m02_syllabus.models import RefSource, RefType
from app.modules.m02_syllabus.reference_clients import (
    CrossRefClient,
    OpenLibraryClient,
    ReferenceClientHTTPError,
    ReferenceClientTimeout,
    _normalize_crossref_item,
    _normalize_ol_doc,
    _safe_str,
)


# ===========================================================================
# _safe_str helper
# ===========================================================================

def test_safe_str_returns_none_for_none():
    assert _safe_str(None) is None


def test_safe_str_returns_none_for_empty():
    assert _safe_str("") is None
    assert _safe_str("   ") is None


def test_safe_str_strips_whitespace():
    assert _safe_str("  hello  ") == "hello"


# ===========================================================================
# _normalize_crossref_item
# ===========================================================================

def _crossref_item(**overrides) -> dict:
    base = {
        "title": ["Data Structures and Algorithms"],
        "author": [
            {"given": "Thomas", "family": "Cormen"},
            {"given": "Charles", "family": "Leiserson"},
        ],
        "published": {"date-parts": [[2022]]},
        "DOI": "10.1234/test.doi",
        "ISBN": ["978-0-262-033848"],
        "URL": "https://doi.org/10.1234/test.doi",
        "publisher": "MIT Press",
    }
    base.update(overrides)
    return base


def test_normalize_crossref_all_fields():
    item = _crossref_item()
    result = _normalize_crossref_item(item, RefType.TEXTBOOK)
    assert result is not None
    assert result.title == "Data Structures and Algorithms"
    assert result.authors == ["Thomas Cormen", "Charles Leiserson"]
    assert result.year == 2022
    assert result.doi == "10.1234/test.doi"
    assert result.isbn == "978-0-262-033848"
    assert result.publisher == "MIT Press"
    assert result.source == RefSource.CROSSREF
    assert result.ref_type == RefType.TEXTBOOK


def test_normalize_crossref_returns_none_without_title():
    item = _crossref_item(title=[])
    assert _normalize_crossref_item(item, RefType.TEXTBOOK) is None


def test_normalize_crossref_handles_missing_author():
    item = _crossref_item(author=None)
    result = _normalize_crossref_item(item, RefType.JOURNAL)
    assert result is not None
    assert result.authors == []


def test_normalize_crossref_handles_missing_year():
    item = _crossref_item(published={})
    result = _normalize_crossref_item(item, RefType.REFERENCE)
    assert result is not None
    assert result.year is None


def test_normalize_crossref_handles_missing_doi():
    item = _crossref_item(DOI=None)
    result = _normalize_crossref_item(item, RefType.TEXTBOOK)
    assert result is not None
    assert result.doi is None


def test_normalize_crossref_ref_type_preserved():
    for rtype in (RefType.TEXTBOOK, RefType.REFERENCE, RefType.JOURNAL, RefType.ONLINE):
        result = _normalize_crossref_item(_crossref_item(), rtype)
        assert result.ref_type == rtype


# ===========================================================================
# _normalize_ol_doc
# ===========================================================================

def _ol_doc(**overrides) -> dict:
    base = {
        "title": "Introduction to Algorithms",
        "author_name": ["Thomas Cormen"],
        "first_publish_year": 2009,
        "isbn": ["978-0-262-033848"],
        "publisher": ["MIT Press"],
        "key": "/works/OL12345W",
    }
    base.update(overrides)
    return base


def test_normalize_ol_all_fields():
    result = _normalize_ol_doc(_ol_doc())
    assert result is not None
    assert result.title == "Introduction to Algorithms"
    assert result.authors == ["Thomas Cormen"]
    assert result.year == 2009
    assert result.isbn == "978-0-262-033848"
    assert result.publisher == "MIT Press"
    assert result.url == "https://openlibrary.org/works/OL12345W"
    assert result.source == RefSource.OPENLIBRARY
    assert result.ref_type == RefType.TEXTBOOK
    assert result.doi is None


def test_normalize_ol_returns_none_without_title():
    assert _normalize_ol_doc(_ol_doc(title=None)) is None
    assert _normalize_ol_doc(_ol_doc(title="")) is None


def test_normalize_ol_handles_missing_year():
    result = _normalize_ol_doc(_ol_doc(first_publish_year=None))
    assert result is not None
    assert result.year is None


def test_normalize_ol_handles_missing_isbn():
    result = _normalize_ol_doc(_ol_doc(isbn=[]))
    assert result is not None
    assert result.isbn is None


def test_normalize_ol_builds_url_from_key():
    result = _normalize_ol_doc(_ol_doc(key="/works/OL99W"))
    assert result.url == "https://openlibrary.org/works/OL99W"


def test_normalize_ol_url_is_none_without_key():
    result = _normalize_ol_doc(_ol_doc(key=None))
    assert result.url is None


# ===========================================================================
# CrossRefClient.search — mocked _get_with_retry
# ===========================================================================

_CROSSREF_RESPONSE = {
    "message": {
        "items": [
            {
                "title": ["Algorithms Unplugged"],
                "author": [{"given": "Berthold", "family": "Vöcking"}],
                "published": {"date-parts": [[2011]]},
                "DOI": "10.1007/978-3-642-15328-0",
                "ISBN": [],
                "URL": "https://doi.org/10.1007/978-3-642-15328-0",
                "publisher": "Springer",
            },
            {
                "title": ["The Art of Computer Programming"],
                "author": [{"given": "Donald", "family": "Knuth"}],
                "published": {"date-parts": [[1997]]},
                "DOI": "10.3210/knuth.v1",
                "ISBN": ["978-0-201-89683-1"],
                "URL": None,
                "publisher": "Addison-Wesley",
            },
        ]
    }
}


@pytest.mark.asyncio
async def test_crossref_search_returns_candidates():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value=_CROSSREF_RESPONSE),
    ):
        client = CrossRefClient(base_url="https://api.crossref.org", max_results=5)
        results = await client.search("algorithms", ref_type=RefType.TEXTBOOK)

    assert len(results) == 2
    assert results[0].title == "Algorithms Unplugged"
    assert results[0].source == RefSource.CROSSREF
    assert results[1].doi == "10.3210/knuth.v1"


@pytest.mark.asyncio
async def test_crossref_search_uses_book_filter_for_textbook():
    captured_params = {}

    async def _mock_get(url, params, **kw):
        captured_params.update(params)
        return {"message": {"items": []}}

    with patch("app.modules.m02_syllabus.reference_clients._get_with_retry", new=_mock_get):
        client = CrossRefClient(base_url="https://api.crossref.org")
        await client.search("test", ref_type=RefType.TEXTBOOK)

    assert captured_params.get("filter") == "type:book"


@pytest.mark.asyncio
async def test_crossref_search_uses_journal_filter():
    captured_params = {}

    async def _mock_get(url, params, **kw):
        captured_params.update(params)
        return {"message": {"items": []}}

    with patch("app.modules.m02_syllabus.reference_clients._get_with_retry", new=_mock_get):
        client = CrossRefClient(base_url="https://api.crossref.org")
        await client.search("test", ref_type=RefType.JOURNAL)

    assert captured_params.get("filter") == "type:journal-article"


@pytest.mark.asyncio
async def test_crossref_search_no_filter_for_online():
    captured_params = {}

    async def _mock_get(url, params, **kw):
        captured_params.update(params)
        return {"message": {"items": []}}

    with patch("app.modules.m02_syllabus.reference_clients._get_with_retry", new=_mock_get):
        client = CrossRefClient(base_url="https://api.crossref.org")
        await client.search("test", ref_type=RefType.ONLINE)

    assert "filter" not in captured_params


@pytest.mark.asyncio
async def test_crossref_search_skips_items_without_title():
    response = {
        "message": {
            "items": [
                {"title": [], "author": [], "published": {}},
                {"title": ["Valid Title"], "author": [], "published": {"date-parts": [[2020]]}},
            ]
        }
    }
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value=response),
    ):
        client = CrossRefClient(base_url="https://api.crossref.org")
        results = await client.search("test")

    assert len(results) == 1
    assert results[0].title == "Valid Title"


@pytest.mark.asyncio
async def test_crossref_search_returns_empty_on_empty_response():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value={"message": {"items": []}}),
    ):
        client = CrossRefClient(base_url="https://api.crossref.org")
        results = await client.search("test")
    assert results == []


@pytest.mark.asyncio
async def test_crossref_raises_http_error_on_4xx():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(side_effect=ReferenceClientHTTPError(404, "Not found")),
    ):
        client = CrossRefClient(base_url="https://api.crossref.org")
        with pytest.raises(ReferenceClientHTTPError) as exc_info:
            await client.search("test")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_crossref_raises_timeout_error():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(side_effect=ReferenceClientTimeout("Timed out")),
    ):
        client = CrossRefClient(base_url="https://api.crossref.org")
        with pytest.raises(ReferenceClientTimeout):
            await client.search("test")


# ===========================================================================
# OpenLibraryClient.search — mocked _get_with_retry
# ===========================================================================

_OL_RESPONSE = {
    "docs": [
        {
            "title": "Structure and Interpretation of Computer Programs",
            "author_name": ["Harold Abelson", "Gerald Jay Sussman"],
            "first_publish_year": 1996,
            "isbn": ["978-0-262-51087-5"],
            "publisher": ["MIT Press"],
            "key": "/works/OL4974715W",
        },
        {
            "title": "The Pragmatic Programmer",
            "author_name": ["David Thomas", "Andrew Hunt"],
            "first_publish_year": 2019,
            "isbn": [],
            "publisher": ["Addison-Wesley"],
            "key": "/works/OL9123456W",
        },
    ]
}


@pytest.mark.asyncio
async def test_ol_search_returns_candidates():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value=_OL_RESPONSE),
    ):
        client = OpenLibraryClient(base_url="https://openlibrary.org")
        results = await client.search("computer programs", limit=5)

    assert len(results) == 2
    assert results[0].title == "Structure and Interpretation of Computer Programs"
    assert results[0].source == RefSource.OPENLIBRARY
    assert results[0].ref_type == RefType.TEXTBOOK
    assert results[1].isbn is None


@pytest.mark.asyncio
async def test_ol_search_passes_correct_params():
    captured_params = {}

    async def _mock_get(url, params, **kw):
        captured_params.update(params)
        return {"docs": []}

    with patch("app.modules.m02_syllabus.reference_clients._get_with_retry", new=_mock_get):
        client = OpenLibraryClient(base_url="https://openlibrary.org")
        await client.search("algorithms", limit=3)

    assert captured_params["q"] == "algorithms"
    assert captured_params["limit"] == 3
    assert "fields" in captured_params


@pytest.mark.asyncio
async def test_ol_search_skips_docs_without_title():
    response = {
        "docs": [
            {"title": None, "author_name": ["Author A"]},
            {"title": "Valid Book", "author_name": ["Author B"], "first_publish_year": 2020},
        ]
    }
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value=response),
    ):
        client = OpenLibraryClient(base_url="https://openlibrary.org")
        results = await client.search("test")

    assert len(results) == 1
    assert results[0].title == "Valid Book"


@pytest.mark.asyncio
async def test_ol_search_returns_empty_on_empty_docs():
    with patch(
        "app.modules.m02_syllabus.reference_clients._get_with_retry",
        new=AsyncMock(return_value={"docs": []}),
    ):
        client = OpenLibraryClient(base_url="https://openlibrary.org")
        results = await client.search("test")
    assert results == []
