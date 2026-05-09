"""
CrossRef and OpenLibrary async HTTP clients for reference enrichment.

Safety contract:
  - All metadata (title, authors, year, DOI, ISBN) comes ONLY from API response fields.
  - Missing fields are set to None — never inferred or generated.
  - No ORM access; no writes; pure I/O with typed output.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from app.config import settings
from app.modules.m02_syllabus.models import RefSource, RefType
from app.modules.m02_syllabus.schemas import ReferenceCandidate

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BASE_BACKOFF  = 1.0   # seconds; doubles each retry: 1 → 2


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ReferenceClientError(Exception):
    """Base for all reference client failures."""


class ReferenceClientTimeout(ReferenceClientError):
    """API call timed out after all retry attempts."""


class ReferenceClientHTTPError(ReferenceClientError):
    """Non-retryable HTTP error (4xx) or server error exhausted retries."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal helpers — normalization (strictly from API fields, never inferred)
# ---------------------------------------------------------------------------

def _safe_str(value: object) -> str | None:
    """Return stripped string or None; never returns empty string."""
    s = str(value).strip() if value is not None else ""
    return s if s else None


def _normalize_crossref_item(item: dict, ref_type: RefType) -> ReferenceCandidate | None:
    """Map one CrossRef work item to ReferenceCandidate. Returns None if unusable."""
    title_list: list = item.get("title") or []
    title = _safe_str(title_list[0]) if title_list else None
    if not title:
        return None

    authors = [
        _safe_str(f"{a.get('given', '')} {a.get('family', '')}".strip())
        for a in (item.get("author") or [])
        if a.get("family")
    ]
    authors = [a for a in authors if a]

    published = (
        item.get("published")
        or item.get("published-print")
        or item.get("published-online")
        or {}
    )
    date_parts: list = (published.get("date-parts") or [[]])[0]
    year: int | None = None
    if date_parts:
        try:
            year = int(date_parts[0])
        except (TypeError, ValueError):
            year = None

    doi     = _safe_str(item.get("DOI"))
    isbn_list: list = item.get("ISBN") or []
    isbn    = _safe_str(isbn_list[0]) if isbn_list else None
    url     = _safe_str(item.get("URL"))
    publisher = _safe_str(item.get("publisher"))

    return ReferenceCandidate(
        title=title,
        authors=authors,
        year=year,
        ref_type=ref_type,
        source=RefSource.CROSSREF,
        doi=doi,
        isbn=isbn,
        url=url,
        publisher=publisher,
    )


def _normalize_ol_doc(doc: dict) -> ReferenceCandidate | None:
    """Map one OpenLibrary search doc to ReferenceCandidate. Returns None if unusable."""
    title = _safe_str(doc.get("title"))
    if not title:
        return None

    authors = [a for a in (doc.get("author_name") or []) if _safe_str(a)]

    year: int | None = None
    year_raw = doc.get("first_publish_year")
    if year_raw is not None:
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            year = None

    isbn_list: list = doc.get("isbn") or []
    isbn = _safe_str(isbn_list[0]) if isbn_list else None

    publisher_list: list = doc.get("publisher") or []
    publisher = _safe_str(publisher_list[0]) if publisher_list else None

    key = _safe_str(doc.get("key"))
    url = f"https://openlibrary.org{key}" if key else None

    return ReferenceCandidate(
        title=title,
        authors=authors,
        year=year,
        ref_type=RefType.TEXTBOOK,
        source=RefSource.OPENLIBRARY,
        doi=None,
        isbn=isbn,
        url=url,
        publisher=publisher,
    )


# ---------------------------------------------------------------------------
# Retry-aware HTTP GET (module-level so tests can patch it)
# ---------------------------------------------------------------------------

async def _get_with_retry(
    url: str,
    params: dict,
    *,
    timeout: float,
    max_attempts: int = _MAX_ATTEMPTS,
    base_backoff: float = _BASE_BACKOFF,
) -> dict:
    """
    Execute an async GET with exponential-backoff retry.

    Retries on:  TimeoutException, ConnectError, and 5xx HTTP status.
    Raises immediately on 4xx (client error — retrying won't help).
    Returns: parsed JSON body as dict.
    """
    last_exc: Exception = ReferenceClientError("No attempts made")

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()

        except httpx.TimeoutException as exc:
            last_exc = ReferenceClientTimeout(
                f"Timeout after {timeout}s reaching {url}"
            )
            logger.warning(
                "reference_client timeout attempt=%d/%d url=%s",
                attempt + 1, max_attempts, url,
            )

        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code < 500:
                # 4xx — client error; no point retrying
                raise ReferenceClientHTTPError(code, f"HTTP {code} from {url}")
            last_exc = ReferenceClientHTTPError(code, f"HTTP {code} from {url}")
            logger.warning(
                "reference_client http_error=%d attempt=%d/%d url=%s",
                code, attempt + 1, max_attempts, url,
            )

        except httpx.RequestError as exc:
            last_exc = ReferenceClientError(
                f"Request error reaching {url}: {exc}"
            )
            logger.warning(
                "reference_client request_error attempt=%d/%d url=%s err=%s",
                attempt + 1, max_attempts, url, str(exc),
            )

        if attempt < max_attempts - 1:
            await asyncio.sleep(base_backoff * (2 ** attempt))

    raise last_exc


# ---------------------------------------------------------------------------
# CrossRefClient
# ---------------------------------------------------------------------------

class CrossRefClient:
    """
    Query the CrossRef REST API for academic references.

    All returned ReferenceCandidate objects contain only data from the API
    response — no fields are inferred or generated.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_results: int | None = None,
    ) -> None:
        self._base_url   = (base_url  or settings.CROSSREF_BASE_URL).rstrip("/")
        self._timeout    = timeout    or settings.REFERENCE_ENRICHMENT_TIMEOUT_SECONDS
        self._max_results = max_results or settings.REFERENCE_ENRICHMENT_MAX_PER_QUERY

    async def search(
        self,
        query: str,
        ref_type: RefType = RefType.TEXTBOOK,
        rows: int | None = None,
    ) -> list[ReferenceCandidate]:
        """
        Search CrossRef works.

        ref_type TEXTBOOK/REFERENCE → filter=type:book
        ref_type JOURNAL            → filter=type:journal-article
        ref_type ONLINE             → no type filter (broad search)
        """
        rows = rows or self._max_results

        type_filter: str | None
        if ref_type in (RefType.TEXTBOOK, RefType.REFERENCE):
            type_filter = "book"
        elif ref_type == RefType.JOURNAL:
            type_filter = "journal-article"
        else:
            type_filter = None

        params: dict = {"query": query, "rows": rows}
        if type_filter:
            params["filter"] = f"type:{type_filter}"

        data = await _get_with_retry(
            f"{self._base_url}/works",
            params=params,
            timeout=self._timeout,
        )

        items: list = (data.get("message") or {}).get("items") or []
        candidates: list[ReferenceCandidate] = []
        for item in items[:rows]:
            candidate = _normalize_crossref_item(item, ref_type)
            if candidate is not None:
                candidates.append(candidate)
        return candidates


# ---------------------------------------------------------------------------
# OpenLibraryClient
# ---------------------------------------------------------------------------

class OpenLibraryClient:
    """
    Query the OpenLibrary Search API for textbooks and references.

    All returned ReferenceCandidate objects contain only data from the API
    response — no fields are inferred or generated.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_results: int | None = None,
    ) -> None:
        self._base_url    = (base_url  or settings.OPENLIBRARY_BASE_URL).rstrip("/")
        self._timeout     = timeout    or settings.REFERENCE_ENRICHMENT_TIMEOUT_SECONDS
        self._max_results = max_results or settings.REFERENCE_ENRICHMENT_MAX_PER_QUERY

    async def search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[ReferenceCandidate]:
        """Search OpenLibrary for books. Always returns RefType.TEXTBOOK results."""
        limit = limit or self._max_results

        data = await _get_with_retry(
            f"{self._base_url}/search.json",
            params={
                "q":      query,
                "limit":  limit,
                "fields": "key,title,author_name,first_publish_year,isbn,publisher",
            },
            timeout=self._timeout,
        )

        docs: list = data.get("docs") or []
        candidates: list[ReferenceCandidate] = []
        for doc in docs[:limit]:
            candidate = _normalize_ol_doc(doc)
            if candidate is not None:
                candidates.append(candidate)
        return candidates
