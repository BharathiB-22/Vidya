"""YouTube Data API v3 source adapter for M05."""
from __future__ import annotations

from typing import Any

import httpx

from app.modules.m05_learning_materials.source_adapters.base import (
    HTTPX_TIMEOUT,
    RawItem,
    SourceAdapterError,
    adapter_retry,
    get_adapter_logger,
)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YouTubeAdapter:
    """Searches YouTube via Data API v3; requires YOUTUBE_API_KEY in settings."""

    def __init__(self, tenant_schema: str) -> None:
        self._tenant_schema = tenant_schema
        self._log = get_adapter_logger(tenant_schema, "YOUTUBE")

    @adapter_retry
    async def _fetch_raw(self, query: str, limit: int) -> list[dict[str, Any]]:
        from app.config import settings  # deferred — keeps module importable without settings

        if not settings.YOUTUBE_API_KEY:
            raise SourceAdapterError("YOUTUBE_API_KEY is not configured")

        params = {
            "key": settings.YOUTUBE_API_KEY,
            "q": query,
            "part": "snippet",
            "type": "video",
            "maxResults": min(limit, 50),
            "relevanceLanguage": "en",
            "safeSearch": "strict",
        }
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
            return resp.json().get("items", [])

    async def search(self, query: str, limit: int) -> list[RawItem]:
        self._log.info("YouTube search query: %r (limit=%d)", query, limit)
        try:
            items = await self._fetch_raw(query, limit)
        except SourceAdapterError:
            raise
        except Exception as exc:
            self._log.warning("YouTube adapter exhausted retries: %s", exc)
            raise SourceAdapterError(f"YouTube search failed: {exc}") from exc

        results: list[RawItem] = []
        for item in items:
            snippet    = item.get("snippet") or {}
            video_id   = (item.get("id") or {}).get("videoId", "")
            if not video_id:
                continue
            title       = (snippet.get("title") or "").strip()
            description = (snippet.get("description") or "").strip()
            thumbnails  = snippet.get("thumbnails") or {}
            results.append(RawItem(
                source_type="YOUTUBE",
                title=title,
                url=f"https://www.youtube.com/watch?v={video_id}",
                raw_text=f"{title} {description}".strip(),
                metadata={
                    "video_id":      video_id,
                    "channel_title": (snippet.get("channelTitle") or ""),
                    "published_at":  (snippet.get("publishedAt") or ""),
                    "thumbnail_url": ((thumbnails.get("medium") or {}).get("url", "")),
                },
            ))
            if len(results) >= limit:
                break

        self._log.info("YouTube adapter: %d results for %r", len(results), query)
        return results
