"""
Celery heavy-queue task: enrich syllabus references via CrossRef + OpenLibrary.

Flow
----
  1. Verify syllabus exists (tenant schema).
  2. Delete all unconfirmed references (idempotent — safe to retry).
  3. For each reference_query from the AI provider:
       a. Call CrossRefClient.search() (TEXTBOOK → book, JOURNAL → journal-article).
       b. Call OpenLibraryClient.search() for TEXTBOOK / REFERENCE only (books only).
       c. Deduplicate candidates across sources by DOI (preferred) or title.
       d. Bulk-create top N as SyllabusReference rows with is_confirmed=False.
     Per-query failures are absorbed (log + continue) so one bad API call does not
     cancel the remaining queries.
  4. Commit, audit REFERENCE_ENRICHMENT_COMPLETED.

On total failure: audit REFERENCE_ENRICHMENT_FAILED, re-raise.
References are enrichment metadata — their absence never blocks the syllabus workflow.
"""
import asyncio
import logging
import sys
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m02.reference_enrichment")

_async_engine = None
_MAX_TOTAL_REFERENCES = 20   # safety cap — prevents bloating per syllabus


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        from app.config import settings
        # NullPool: no connection caching between asyncio.run() calls.
        # Prevents "Future attached to a different loop" on Windows --pool=solo.
        _async_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.enrich_references",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def enrich_references(
    *,
    job_id: str | None,
    syllabus_id: str,
    tenant_id: str,
    schema_name: str,
    reference_queries: list[dict],
    replace_types: list[str] | None = None,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    """Fetch real bibliographic metadata for the AI's search queries.

    `replace_types` scopes which part of the bibliography is cleared before the new
    references land. A BOOKS regeneration passes ["TEXTBOOK"], so the Reference
    Books and Web Resources the Board was happy with survive it. None (a full
    generation) clears the whole unconfirmed bibliography.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_enrichment(
            syllabus_id=UUID(syllabus_id),
            tenant_id=UUID(tenant_id),
            schema_name=schema_name,
            reference_queries=reference_queries,
            replace_types=replace_types,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_enrichment(
    syllabus_id: UUID,
    tenant_id: UUID,
    schema_name: str,
    reference_queries: list[dict],
    replace_types: list[str] | None = None,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m02_syllabus.models import RefSource, RefType
    from app.modules.m02_syllabus.reference_clients import CrossRefClient, OpenLibraryClient
    from app.modules.m02_syllabus.repository import (
        SyllabusReferenceRepository,
        SyllabusRepository,
    )

    engine = _get_async_engine()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text(f"SET search_path TO {schema_name}, public"))

            # ------------------------------------------------------------------
            # Verify syllabus still exists
            # ------------------------------------------------------------------
            syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=session)
            if syllabus is None:
                raise ValueError(
                    f"Syllabus {syllabus_id} not found in schema {schema_name!r}."
                )

            # ------------------------------------------------------------------
            # Idempotent cleanup: delete the unconfirmed references this run is
            # about to replace. Confirmed references are Board-curated and are
            # never touched.
            #
            # `replace_types` scopes the clear. A BOOKS regeneration rewrites the
            # Text Books alone, so it must not take the Reference Books and Web
            # Resources down with them — the Board did not ask to lose those, and
            # would have no way of knowing they had gone.
            # ------------------------------------------------------------------
            scoped_types: list[RefType] = []
            for name in (replace_types or []):
                try:
                    scoped_types.append(RefType(name))
                except ValueError:
                    logger.warning("m02.enrich: ignoring unknown ref_type %r in replace_types", name)

            deleted = await SyllabusReferenceRepository.delete_all_unconfirmed(
                syllabus_id, db=session, ref_types=scoped_types or None,
            )
            if deleted:
                logger.info(
                    "m02.enrich: cleared %d stale unconfirmed references "
                    "(syllabus=%s scope=%s)",
                    deleted, syllabus_id,
                    [t.value for t in scoped_types] or "ALL",
                )

            # ------------------------------------------------------------------
            # Fetch and store references for each query
            # ------------------------------------------------------------------
            crossref_client = CrossRefClient()
            ol_client       = OpenLibraryClient()
            total_created   = 0

            for rq in reference_queries:
                if total_created >= _MAX_TOTAL_REFERENCES:
                    logger.info(
                        "m02.enrich: reached cap=%d, stopping early (syllabus=%s)",
                        _MAX_TOTAL_REFERENCES, syllabus_id,
                    )
                    break

                query_str = rq.get("query_str", "")
                ref_type_str = rq.get("ref_type", "TEXTBOOK")
                try:
                    ref_type = RefType(ref_type_str)
                except ValueError:
                    ref_type = RefType.TEXTBOOK

                candidates: list = []
                seen: set[str] = set()   # dedup key: doi or normalised title

                # CrossRef covers TEXTBOOK, REFERENCE, JOURNAL
                try:
                    cr_results = await crossref_client.search(query_str, ref_type=ref_type)
                    for c in cr_results:
                        key = c.doi or c.title.lower()
                        if key not in seen:
                            seen.add(key)
                            candidates.append(c)
                except Exception as exc:
                    logger.warning(
                        "m02.enrich: CrossRef failed for query %r: %s",
                        query_str[:60], exc,
                    )

                # OpenLibrary covers TEXTBOOK and REFERENCE (books only)
                if ref_type in (RefType.TEXTBOOK, RefType.REFERENCE):
                    try:
                        ol_results = await ol_client.search(query_str)
                        for c in ol_results:
                            key = c.doi or c.title.lower()
                            if key not in seen:
                                seen.add(key)
                                candidates.append(c)
                    except Exception as exc:
                        logger.warning(
                            "m02.enrich: OpenLibrary failed for query %r: %s",
                            query_str[:60], exc,
                        )

                if not candidates:
                    logger.info(
                        "m02.enrich: no candidates for query %r (syllabus=%s)",
                        query_str[:60], syllabus_id,
                    )
                    continue

                # Cap per-query at remaining budget
                slots = _MAX_TOTAL_REFERENCES - total_created
                candidates = candidates[:slots]

                ref_items = [
                    {
                        "title":        c.title,
                        "authors":      c.authors,
                        "year":         c.year,
                        "ref_type":     c.ref_type,
                        "source":       c.source,
                        "doi":          c.doi,
                        "isbn":         c.isbn,
                        "url":          c.url,
                        "publisher":    c.publisher,
                        "is_confirmed": False,
                    }
                    for c in candidates
                ]

                created = await SyllabusReferenceRepository.bulk_create(
                    syllabus_id, ref_items, db=session
                )
                total_created += len(created)

                logger.info(
                    "m02.enrich: query %r -> %d references (syllabus=%s)",
                    query_str[:60], len(created), syllabus_id,
                )

            await session.commit()

        # ------------------------------------------------------------------
        # Audit: REFERENCE_ENRICHMENT_COMPLETED
        # ------------------------------------------------------------------
        await AuditService.log(
            AuditEventType.REFERENCE_ENRICHMENT_COMPLETED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="Syllabus",
            target_id=str(syllabus_id),
            metadata={
                "references_created": total_created,
                "queries_processed":  len(reference_queries),
            },
        )

        logger.info(
            "m02.enrich: complete (syllabus=%s total_refs=%d)",
            syllabus_id, total_created,
        )

        return {
            "syllabus_id":        str(syllabus_id),
            "references_created": total_created,
            "queries_processed":  len(reference_queries),
        }

    except Exception as exc:
        try:
            await AuditService.log(
                AuditEventType.REFERENCE_ENRICHMENT_FAILED,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=schema_name,
                target_entity="Syllabus",
                target_id=str(syllabus_id),
                metadata={"error": str(exc)[:500]},
            )
        except Exception:
            logger.exception("m02.enrich: failed to log REFERENCE_ENRICHMENT_FAILED audit")

        raise
