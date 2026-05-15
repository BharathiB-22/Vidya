"""NPTEL public website source adapter for M05.

NPTEL does not publish a stable public JSON API.  This adapter fetches the
NPTEL course-search page, which is a Next.js app that embeds course data in
a <script id="__NEXT_DATA__"> tag.  Parsing is deliberately defensive:
any parse failure returns [] instead of raising, because the page structure
may change without notice.

Only network errors (after retries exhausted) raise SourceAdapterError.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.modules.m05_learning_materials.source_adapters.base import (
    HTTPX_TIMEOUT,
    RawItem,
    SourceAdapterError,
    adapter_retry,
    get_adapter_logger,
)

_SEARCH_URL   = "https://nptel.ac.in/courses"
_USER_AGENT   = "VidyaEducationBot/1.0 (+https://vidya.local; educational use)"
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


class NptelAdapter:
    """Best-effort NPTEL course search via website scraping."""

    def __init__(self, tenant_schema: str) -> None:
        self._tenant_schema = tenant_schema
        self._log = get_adapter_logger(tenant_schema, "NPTEL")

    @adapter_retry
    async def _fetch_html(self, query: str) -> str:
        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                _SEARCH_URL,
                params={"searchText": query},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def _extract_courses(html: str, limit: int) -> list[dict[str, Any]]:
        """Pull course records from Next.js __NEXT_DATA__; returns [] on any failure."""
        m = _NEXT_DATA_RE.search(html)
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []
        page_props = (data.get("props") or {}).get("pageProps") or {}
        candidates: list[Any] = (
            page_props.get("courses")
            or page_props.get("courseList")
            or (page_props.get("data") or {}).get("courses")
            or []
        )
        if not isinstance(candidates, list):
            return []
        return candidates[:limit]

    @staticmethod
    def _item_from_course(raw: dict[str, Any]) -> RawItem | None:
        """Convert one NPTEL course dict to RawItem; returns None if unusable."""
        if not isinstance(raw, dict):
            return None
        title = (
            raw.get("courseName")
            or raw.get("name")
            or raw.get("title")
            or ""
        ).strip()
        if not title:
            return None

        course_id = raw.get("courseId") or raw.get("id") or ""
        url = (
            raw.get("url")
            or (f"https://nptel.ac.in/courses/{course_id}" if course_id else None)
        )

        instructor: Any = (
            raw.get("coordinators")
            or raw.get("instructor")
            or raw.get("facultyName")
            or ""
        )
        if isinstance(instructor, list):
            instructor = ", ".join(
                (i.get("name") if isinstance(i, dict) else str(i))
                for i in instructor
                if i
            )

        description = (raw.get("courseDescription") or raw.get("description") or "").strip()
        return RawItem(
            source_type="NPTEL",
            title=title,
            url=url,
            raw_text=f"{title} {description}".strip(),
            metadata={
                "course_name": title,
                "instructor":  str(instructor),
                "institution": (raw.get("institute") or raw.get("institution") or "IIT/IISc"),
                "duration":    (raw.get("duration") or raw.get("totalWeeks") or ""),
            },
        )

    async def search(self, query: str, limit: int) -> list[RawItem]:
        try:
            html = await self._fetch_html(query)
        except SourceAdapterError:
            raise
        except Exception as exc:
            self._log.warning("NPTEL adapter exhausted retries: %s", exc)
            raise SourceAdapterError(f"NPTEL fetch failed: {exc}") from exc

        raw_courses = self._extract_courses(html, limit)
        results: list[RawItem] = []
        for raw in raw_courses:
            item = self._item_from_course(raw)
            if item is not None:
                results.append(item)
            if len(results) >= limit:
                break

        if not results:
            self._log.warning(
                "NPTEL adapter: no courses parsed — page structure may have changed"
            )
        else:
            self._log.info("NPTEL adapter: %d results for %r", len(results), query)
        return results
