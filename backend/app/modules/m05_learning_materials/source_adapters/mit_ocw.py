"""MIT OpenCourseWare source adapter for M05.

MIT OCW serves a Next.js search page that embeds result data in a
<script id="__NEXT_DATA__"> tag.  This adapter fetches that page and
extracts course records defensively: parse failures return [] rather than
raising, because the page structure may change without notice.

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

_BASE_URL      = "https://ocw.mit.edu"
_SEARCH_URL    = f"{_BASE_URL}/search/"
_USER_AGENT    = "VidyaEducationBot/1.0 (+https://vidya.local; educational use)"
_NEXT_DATA_RE  = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


class MitOcwAdapter:
    """Best-effort MIT OCW course search via website scraping."""

    def __init__(self, tenant_schema: str) -> None:
        self._tenant_schema = tenant_schema
        self._log = get_adapter_logger(tenant_schema, "MIT_OCW")

    @adapter_retry
    async def _fetch_html(self, query: str) -> str:
        headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                _SEARCH_URL,
                params={"q": query},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def _extract_results(html: str, limit: int) -> list[dict[str, Any]]:
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
            page_props.get("results")
            or page_props.get("courses")
            or (page_props.get("data") or {}).get("results")
            or []
        )
        if not isinstance(candidates, list):
            return []
        return candidates[:limit]

    @staticmethod
    def _item_from_result(raw: dict[str, Any]) -> RawItem | None:
        """Convert one MIT OCW result dict to RawItem; returns None if unusable."""
        if not isinstance(raw, dict):
            return None
        title = (
            raw.get("title")
            or raw.get("course_title")
            or raw.get("name")
            or ""
        ).strip()
        if not title:
            return None

        slug = raw.get("url") or raw.get("slug") or raw.get("id") or ""
        url: str | None = (
            slug if slug.startswith("http")
            else (f"{_BASE_URL}{slug}" if slug else None)
        )

        description = (raw.get("description") or raw.get("short_description") or "").strip()
        return RawItem(
            source_type="MIT_OCW",
            title=title,
            url=url,
            raw_text=f"{title} {description}".strip(),
            metadata={
                "course_number": (raw.get("course_num") or raw.get("number") or ""),
                "department":    (raw.get("department") or raw.get("departments") or ""),
                "level":         (raw.get("level") or raw.get("course_level") or ""),
                "resource_type": (raw.get("object_type") or raw.get("resource_type") or "Course"),
            },
        )

    async def search(self, query: str, limit: int) -> list[RawItem]:
        try:
            html = await self._fetch_html(query)
        except SourceAdapterError:
            raise
        except Exception as exc:
            self._log.warning("MIT OCW adapter exhausted retries: %s", exc)
            raise SourceAdapterError(f"MIT OCW fetch failed: {exc}") from exc

        raw_results = self._extract_results(html, limit)
        results: list[RawItem] = []
        for raw in raw_results:
            item = self._item_from_result(raw)
            if item is not None:
                results.append(item)
            if len(results) >= limit:
                break

        if not results:
            self._log.warning(
                "MIT OCW adapter: no results parsed — page structure may have changed"
            )
        else:
            self._log.info("MIT OCW adapter: %d results for %r", len(results), query)
        return results
