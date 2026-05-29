"""arXiv public Atom API source adapter for M05."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from app.modules.m05_learning_materials.source_adapters.base import (
    HTTPX_TIMEOUT,
    RawItem,
    SourceAdapterError,
    adapter_retry,
    get_adapter_logger,
)

_SEARCH_URL = "https://export.arxiv.org/api/query"
_ATOM_NS    = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivAdapter:
    """Searches arXiv via its public Atom API — no API key required."""

    def __init__(self, tenant_schema: str) -> None:
        self._tenant_schema = tenant_schema
        self._log = get_adapter_logger(tenant_schema, "ARXIV")

    @adapter_retry
    async def _fetch_raw(self, query: str, limit: int) -> str:
        # Query is passed as-is; callers now supply proper arXiv Boolean syntax
        # (e.g. ti:"..." AND cat:cs.AI) rather than the old all:... fallback.
        params = {
            "search_query": query,
            "start":        0,
            "max_results":  limit,
            "sortBy":       "relevance",
            "sortOrder":    "descending",
        }
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            if resp.status_code == 429:
                raise SourceAdapterError("arXiv rate-limited (429); retry later")
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def _parse_atom(xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        results: list[dict] = []
        for entry in root.findall("atom:entry", _ATOM_NS):
            id_text   = (entry.findtext("atom:id",        "", _ATOM_NS) or "").strip()
            title     = (entry.findtext("atom:title",     "", _ATOM_NS) or "").strip()
            summary   = (entry.findtext("atom:summary",   "", _ATOM_NS) or "").strip()
            published = (entry.findtext("atom:published", "", _ATOM_NS) or "").strip()
            arxiv_id  = id_text.split("/abs/")[-1] if "/abs/" in id_text else ""
            authors   = [
                a.findtext("atom:name", "", _ATOM_NS) or ""
                for a in entry.findall("atom:author", _ATOM_NS)
            ]
            page_url = None
            pdf_url  = None
            for link in entry.findall("atom:link", _ATOM_NS):
                rel  = link.get("rel",  "")
                href = link.get("href", "")
                mime = link.get("type", "")
                if rel == "alternate":
                    page_url = href
                elif mime == "application/pdf" or (rel == "related" and "pdf" in href):
                    pdf_url = href
            results.append({
                "arxiv_id":  arxiv_id,
                "title":     title,
                "summary":   summary,
                "published": published,
                "authors":   [a for a in authors if a],
                "page_url":  page_url or id_text,
                "pdf_url":   pdf_url,
            })
        return results

    async def search(self, query: str, limit: int) -> list[RawItem]:
        self._log.info("arXiv search query: %r (limit=%d)", query, limit)
        try:
            xml_text = await self._fetch_raw(query, limit)
        except SourceAdapterError:
            raise
        except Exception as exc:
            self._log.warning("arXiv adapter exhausted retries: %s", exc)
            raise SourceAdapterError(f"arXiv search failed: {exc}") from exc

        try:
            entries = self._parse_atom(xml_text)
        except ET.ParseError as exc:
            self._log.warning("arXiv XML parse error: %s", exc)
            raise SourceAdapterError(f"arXiv XML parsing failed: {exc}") from exc

        results: list[RawItem] = []
        for e in entries:
            if not e["title"]:
                continue
            results.append(RawItem(
                source_type="ARXIV",
                title=e["title"],
                url=e["page_url"],
                raw_text=f"{e['title']} {e['summary']}".strip(),
                metadata={
                    "arxiv_id":        e["arxiv_id"],
                    "authors":         e["authors"],
                    "published_at":    e["published"],
                    "pdf_url":         e["pdf_url"],
                    "abstract_snippet": e["summary"][:500],
                },
            ))

        self._log.info("arXiv adapter: %d results for %r", len(results), query)
        return results
