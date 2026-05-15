"""STEP-05 smoke tests — M05 source adapter implementations.

All HTTP calls are mocked; no real network requests are made.
asyncio.sleep is patched to make tenacity retries instant.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import asyncio
import os

os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("YOUTUBE_API_KEY","test-yt-key")

from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.m05_learning_materials.source_adapters import (
    AbstractSourceAdapter,
    ArxivAdapter,
    MitOcwAdapter,
    NptelAdapter,
    RawItem,
    SourceAdapterError,
    YouTubeAdapter,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


def _json_resp(payload: dict) -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=payload)
    return r


def _text_resp(text: str) -> MagicMock:
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.text = text
    return r


def _mock_client(response) -> AsyncMock:
    """Build an async httpx.AsyncClient context-manager mock."""
    c = AsyncMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__  = AsyncMock(return_value=False)
    c.get        = AsyncMock(return_value=response)
    return c


def _failing_client() -> AsyncMock:
    c = AsyncMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__  = AsyncMock(return_value=False)
    c.get        = AsyncMock(side_effect=Exception("network error"))
    return c


def run(coro):
    return asyncio.run(coro)


# ===========================================================================
# YouTube
# ===========================================================================
print("\n--- YouTube ---")

_YT_PAYLOAD = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title":        "ML Lecture 1",
                "description":  "Intro to machine learning",
                "channelTitle": "NPTEL Online",
                "publishedAt":  "2023-01-15T10:00:00Z",
                "thumbnails":   {"medium": {"url": "https://img.youtube.com/vi/abc123/mqdefault.jpg"}},
            },
        }
    ]
}

yt = YouTubeAdapter(tenant_schema="tenant_test")

# 1. Constructor sets tenant_schema and satisfies protocol
check("YouTubeAdapter satisfies AbstractSourceAdapter",
      isinstance(yt, AbstractSourceAdapter))

# 2. search() returns correct RawItem from mocked response
with patch("httpx.AsyncClient", return_value=_mock_client(_json_resp(_YT_PAYLOAD))):
    items = run(yt.search("machine learning", 5))

check("YouTube: 1 item returned", len(items) == 1)
item = items[0]
check("YouTube: source_type=YOUTUBE",         item.source_type == "YOUTUBE")
check("YouTube: url contains videoId",         item.url == "https://www.youtube.com/watch?v=abc123")
check("YouTube: metadata.video_id",            item.metadata["video_id"] == "abc123")
check("YouTube: metadata.channel_title",       item.metadata["channel_title"] == "NPTEL Online")
check("YouTube: metadata.published_at",        item.metadata["published_at"] == "2023-01-15T10:00:00Z")
check("YouTube: metadata.thumbnail_url set",   "mqdefault" in item.metadata["thumbnail_url"])
check("YouTube: raw_text contains title",       "ML Lecture 1" in item.raw_text)

# 3. Items with no videoId are silently skipped
with patch("httpx.AsyncClient",
           return_value=_mock_client(_json_resp({"items": [{"id": {}, "snippet": {"title": "X"}}]}))):
    no_id = run(yt.search("test", 5))
check("YouTube: item with no videoId skipped", no_id == [])

# 4. Network failure → SourceAdapterError (retries instant via asyncio.sleep mock)
with patch("asyncio.sleep", new_callable=AsyncMock):
    with patch("httpx.AsyncClient", return_value=_failing_client()):
        try:
            run(yt.search("test", 5))
            check("YouTube: SourceAdapterError on network failure", False)
        except SourceAdapterError:
            check("YouTube: SourceAdapterError on network failure", True)

# ===========================================================================
# arXiv
# ===========================================================================
print("\n--- arXiv ---")

_ARXIV_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Deep Learning for Beginners</title>
    <summary>An introduction to deep learning methods and applications.</summary>
    <published>2023-01-01T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2301.00001v1"/>
    <link rel="related" type="application/pdf" href="http://arxiv.org/pdf/2301.00001v1"/>
  </entry>
</feed>
"""

arx = ArxivAdapter(tenant_schema="tenant_test")
check("ArxivAdapter satisfies AbstractSourceAdapter",
      isinstance(arx, AbstractSourceAdapter))

with patch("httpx.AsyncClient", return_value=_mock_client(_text_resp(_ARXIV_XML))):
    arx_items = run(arx.search("deep learning", 5))

check("arXiv: 1 item returned",               len(arx_items) == 1)
ai = arx_items[0]
check("arXiv: source_type=ARXIV",             ai.source_type == "ARXIV")
check("arXiv: title correct",                  ai.title == "Deep Learning for Beginners")
check("arXiv: url = abs page",                 ai.url == "http://arxiv.org/abs/2301.00001v1")
check("arXiv: metadata.arxiv_id",             ai.metadata["arxiv_id"] == "2301.00001v1")
check("arXiv: metadata.authors list",          "Alice Smith" in ai.metadata["authors"])
check("arXiv: metadata.published_at",          ai.metadata["published_at"] == "2023-01-01T00:00:00Z")
check("arXiv: metadata.pdf_url",               ai.metadata["pdf_url"] == "http://arxiv.org/pdf/2301.00001v1")
check("arXiv: metadata.abstract_snippet max500", len(ai.metadata["abstract_snippet"]) <= 500)
check("arXiv: raw_text contains title",        "Deep Learning" in ai.raw_text)

# Network failure
with patch("asyncio.sleep", new_callable=AsyncMock):
    with patch("httpx.AsyncClient", return_value=_failing_client()):
        try:
            run(arx.search("test", 5))
            check("arXiv: SourceAdapterError on network failure", False)
        except SourceAdapterError:
            check("arXiv: SourceAdapterError on network failure", True)

# ===========================================================================
# NPTEL
# ===========================================================================
print("\n--- NPTEL ---")

_NPTEL_HTML = """<!DOCTYPE html><html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "courses": [
        {
          "courseId": "106104100",
          "courseName": "Programming in Python",
          "courseDescription": "Learn Python programming from scratch.",
          "coordinators": [{"name": "Prof. Raghunath"}],
          "institute": "IIT Madras",
          "totalWeeks": 12
        }
      ]
    }
  }
}
</script>
</body></html>"""

nptel = NptelAdapter(tenant_schema="tenant_test")
check("NptelAdapter satisfies AbstractSourceAdapter",
      isinstance(nptel, AbstractSourceAdapter))

with patch("httpx.AsyncClient", return_value=_mock_client(_text_resp(_NPTEL_HTML))):
    nptel_items = run(nptel.search("python", 5))

check("NPTEL: 1 item returned",               len(nptel_items) == 1)
ni = nptel_items[0]
check("NPTEL: source_type=NPTEL",             ni.source_type == "NPTEL")
check("NPTEL: title correct",                  ni.title == "Programming in Python")
check("NPTEL: url contains courseId",          "106104100" in (ni.url or ""))
check("NPTEL: metadata.instructor",            ni.metadata["instructor"] == "Prof. Raghunath")
check("NPTEL: metadata.institution",           ni.metadata["institution"] == "IIT Madras")
check("NPTEL: metadata.duration",             ni.metadata["duration"] == 12)
check("NPTEL: metadata.course_name",           ni.metadata["course_name"] == "Programming in Python")

# Parse failure returns [] — NOT SourceAdapterError
with patch("httpx.AsyncClient",
           return_value=_mock_client(_text_resp("<html><body>no data</body></html>"))):
    empty = run(nptel.search("test", 5))
check("NPTEL: empty list on parse failure (no raise)", empty == [])

# Network failure → SourceAdapterError
with patch("asyncio.sleep", new_callable=AsyncMock):
    with patch("httpx.AsyncClient", return_value=_failing_client()):
        try:
            run(nptel.search("test", 5))
            check("NPTEL: SourceAdapterError on network failure", False)
        except SourceAdapterError:
            check("NPTEL: SourceAdapterError on network failure", True)

# ===========================================================================
# MIT OCW
# ===========================================================================
print("\n--- MIT OCW ---")

_OCW_HTML = """<!DOCTYPE html><html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{
  "props": {
    "pageProps": {
      "results": [
        {
          "title":       "Introduction to Algorithms",
          "url":         "/courses/6-006-introduction-to-algorithms-spring-2020/",
          "description": "This course covers algorithm design and analysis.",
          "course_num":  "6.006",
          "department":  "Electrical Engineering and Computer Science",
          "level":       "Undergraduate",
          "object_type": "Course"
        }
      ]
    }
  }
}
</script>
</body></html>"""

ocw = MitOcwAdapter(tenant_schema="tenant_test")
check("MitOcwAdapter satisfies AbstractSourceAdapter",
      isinstance(ocw, AbstractSourceAdapter))

with patch("httpx.AsyncClient", return_value=_mock_client(_text_resp(_OCW_HTML))):
    ocw_items = run(ocw.search("algorithms", 5))

check("MIT OCW: 1 item returned",             len(ocw_items) == 1)
oi = ocw_items[0]
check("MIT OCW: source_type=MIT_OCW",         oi.source_type == "MIT_OCW")
check("MIT OCW: title correct",                oi.title == "Introduction to Algorithms")
check("MIT OCW: url fully qualified",
      oi.url == "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/")
check("MIT OCW: metadata.course_number",       oi.metadata["course_number"] == "6.006")
check("MIT OCW: metadata.department",
      oi.metadata["department"] == "Electrical Engineering and Computer Science")
check("MIT OCW: metadata.level",               oi.metadata["level"] == "Undergraduate")
check("MIT OCW: metadata.resource_type",       oi.metadata["resource_type"] == "Course")

# Parse failure returns []
with patch("httpx.AsyncClient",
           return_value=_mock_client(_text_resp("<html><body>no data</body></html>"))):
    empty_ocw = run(ocw.search("test", 5))
check("MIT OCW: empty list on parse failure (no raise)", empty_ocw == [])

# Network failure → SourceAdapterError
with patch("asyncio.sleep", new_callable=AsyncMock):
    with patch("httpx.AsyncClient", return_value=_failing_client()):
        try:
            run(ocw.search("test", 5))
            check("MIT OCW: SourceAdapterError on network failure", False)
        except SourceAdapterError:
            check("MIT OCW: SourceAdapterError on network failure", True)

# ===========================================================================
# Cross-adapter: limit respected
# ===========================================================================
print("\n--- limit contract ---")

_YT_MANY = {
    "items": [
        {"id": {"videoId": f"v{i}"}, "snippet": {"title": f"Video {i}", "description": ""}}
        for i in range(10)
    ]
}
with patch("httpx.AsyncClient", return_value=_mock_client(_json_resp(_YT_MANY))):
    limited = run(yt.search("test", 3))
check("YouTube: limit=3 returns at most 3 items", len(limited) <= 3)

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*52}")
print(f"STEP-05 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL — fix issues above before proceeding.")
    sys.exit(1)
else:
    print("ALL PASS — STEP-05 smoke tests green.")
