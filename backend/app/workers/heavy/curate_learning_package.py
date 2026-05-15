"""
Celery heavy-queue task: curate a learning package for one syllabus unit.

Flow
----
  1. Load the package (must exist in PENDING or CURATING).
  2. Load the syllabus unit to build the unit context string.
  3. Transition package status -> CURATING.
  4. Run all 4 source adapters in parallel; catch SourceAdapterError per adapter
     (partial failure: log warning, continue with partial results).
  5. Abort if zero items collected across all adapters.
  6. Rank items semantically using score_items() (embedder).
  7. Slice to top_n; assign display_order and relevance_score.
  8. Delete any pre-existing items (idempotent on retry).
  9. Bulk-create ranked items via PackageItemRepository.bulk_create().
 10. Transition package status -> READY (item_count = len(items)).
 11. Commit, then audit LEARNING_PACKAGE_CURATION_COMPLETED.

On failure:
  - Reset package status -> PENDING (so faculty can retry).
  - Audit LEARNING_PACKAGE_CURATION_FAILED.
  - Re-raise so Celery marks the task FAILED.
"""
import asyncio
import hashlib
import logging
import sys
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m05.curate_learning_package")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.curate_learning_package",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def curate_learning_package(
    *,
    job_id: str,
    package_id: str,
    tenant_id: str,
    tenant_schema: str,
    syllabus_id: str,
    unit_number: int,
    top_n: int | None = None,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_curation(
            package_id=UUID(package_id),
            tenant_id=UUID(tenant_id),
            tenant_schema=tenant_schema,
            syllabus_id=UUID(syllabus_id),
            unit_number=unit_number,
            top_n=top_n,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_curation(
    package_id: UUID,
    tenant_id: UUID,
    tenant_schema: str,
    syllabus_id: UUID,
    unit_number: int,
    top_n: int | None,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import settings
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m02_syllabus.repository import SyllabusUnitRepository
    from app.modules.m05_learning_materials.embedder import EmbedderError, score_items
    from app.modules.m05_learning_materials.models import PackageStatus
    from app.modules.m05_learning_materials.repository import (
        LearningPackageRepository,
        PackageItemRepository,
    )
    from app.modules.m05_learning_materials.source_adapters import (
        ArxivAdapter,
        MitOcwAdapter,
        NptelAdapter,
        SourceAdapterError,
        YouTubeAdapter,
    )

    _log_extra = {
        "tenant_schema": tenant_schema,
        "package_id":    str(package_id),
        "syllabus_id":   str(syllabus_id),
        "unit_number":   unit_number,
    }

    engine = _get_async_engine()

    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(
                text(f"SET search_path TO {tenant_schema}, public")
            )

            # ------------------------------------------------------------------
            # 1. Load package
            # ------------------------------------------------------------------
            pkg = await LearningPackageRepository.get_by_id(package_id, db=session)
            if pkg is None:
                raise ValueError(
                    f"LearningPackage {package_id} not found in schema {tenant_schema!r}."
                )
            if pkg.status not in (PackageStatus.PENDING, PackageStatus.CURATING):
                raise ValueError(
                    f"LearningPackage {package_id} is {pkg.status.value}; "
                    "curation requires PENDING or CURATING status."
                )

            effective_top_n = top_n if top_n is not None else (pkg.top_n or settings.M05_TOP_N_PER_UNIT)

            # ------------------------------------------------------------------
            # 2. Load syllabus unit for context string
            # ------------------------------------------------------------------
            unit = await SyllabusUnitRepository.get_by_number(
                syllabus_id, unit_number, db=session
            )
            if unit is None:
                raise ValueError(
                    f"SyllabusUnit {unit_number} not found in syllabus {syllabus_id}."
                )

            topic_titles = [
                t["title"] if isinstance(t, dict) else str(t)
                for t in (unit.topics or [])
            ]
            unit_context = f"{unit.title}. Topics: {', '.join(topic_titles)}" if topic_titles else unit.title

            # ------------------------------------------------------------------
            # 3. Transition -> CURATING
            # ------------------------------------------------------------------
            prompt_text = f"unit:{unit_number} syllabus:{syllabus_id} context:{unit_context}"
            prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()
            ai_model = "text-embedding-004"

            if pkg.status != PackageStatus.CURATING:
                await LearningPackageRepository.set_curating(
                    package_id,
                    ai_model=ai_model,
                    prompt_hash=prompt_hash,
                    db=session,
                )
                await session.flush()

            logger.info(
                "m05.curate: started (top_n=%d context=%r)",
                effective_top_n,
                unit_context[:80],
                extra=_log_extra,
            )

            # ------------------------------------------------------------------
            # 4. Run all 4 adapters; tolerate per-adapter failures
            # ------------------------------------------------------------------
            adapters = [
                ("youtube", YouTubeAdapter(tenant_schema=tenant_schema)),
                ("arxiv",   ArxivAdapter(tenant_schema=tenant_schema)),
                ("nptel",   NptelAdapter(tenant_schema=tenant_schema)),
                ("mit_ocw", MitOcwAdapter(tenant_schema=tenant_schema)),
            ]

            all_raw_items = []
            failed_providers: list[str] = []

            async def _fetch(name: str, adapter) -> None:
                try:
                    items = await adapter.search(unit_context, limit=effective_top_n * 2)
                    logger.info(
                        "m05.curate: adapter %s returned %d items",
                        name, len(items),
                        extra={**_log_extra, "source_provider": name},
                    )
                    all_raw_items.extend(items)
                except SourceAdapterError as exc:
                    failed_providers.append(name)
                    logger.warning(
                        "m05.curate: adapter %s failed (%s); continuing with partial results",
                        name, exc,
                        extra={**_log_extra, "source_provider": name},
                    )

            await asyncio.gather(*[_fetch(name, adapter) for name, adapter in adapters])

            if not all_raw_items:
                raise RuntimeError(
                    f"All source adapters failed for package {package_id}. "
                    f"Failed providers: {failed_providers}"
                )

            logger.info(
                "m05.curate: %d raw items collected from %d provider(s); %d failed",
                len(all_raw_items),
                len(adapters) - len(failed_providers),
                len(failed_providers),
                extra=_log_extra,
            )

            # ------------------------------------------------------------------
            # 5. Semantic ranking
            # ------------------------------------------------------------------
            try:
                ranked = await score_items(
                    unit_context,
                    all_raw_items,
                    tenant_schema=tenant_schema,
                    package_id=str(package_id),
                )
            except EmbedderError as exc:
                raise RuntimeError(
                    f"Embedding/ranking failed for package {package_id}: {exc}"
                ) from exc

            top_items = ranked[:effective_top_n]

            logger.info(
                "m05.curate: ranked %d items, keeping top %d",
                len(ranked), len(top_items),
                extra=_log_extra,
            )

            # ------------------------------------------------------------------
            # 6. Delete any pre-existing items (idempotent on retry)
            # ------------------------------------------------------------------
            deleted = await PackageItemRepository.delete_all_for_package(
                package_id, db=session
            )
            if deleted:
                logger.info(
                    "m05.curate: deleted %d pre-existing items (retry path)",
                    deleted,
                    extra=_log_extra,
                )

            # ------------------------------------------------------------------
            # 7. Bulk-create ranked items
            # ------------------------------------------------------------------
            items_data = [
                {
                    "source_type":    raw.source_type,
                    "title":          raw.title,
                    "url":            raw.url,
                    "content_hash":   _content_hash(raw),
                    "metadata":       raw.metadata,
                    "relevance_score": score,
                    "display_order":  idx,
                    "faculty_recommended": False,
                    "added_by_user_id":   None,
                }
                for idx, (raw, score) in enumerate(top_items)
            ]
            new_items = await PackageItemRepository.bulk_create(
                package_id, items_data, db=session
            )
            logger.info(
                "m05.curate: inserted %d items", len(new_items), extra=_log_extra
            )

            # ------------------------------------------------------------------
            # 8. Transition -> READY
            # ------------------------------------------------------------------
            await LearningPackageRepository.set_ready(
                package_id, item_count=len(new_items), db=session
            )

            await session.commit()

        # ------------------------------------------------------------------
        # 9. Audit: LEARNING_PACKAGE_CURATION_COMPLETED
        # ------------------------------------------------------------------
        await AuditService.log(
            AuditEventType.LEARNING_PACKAGE_CURATION_COMPLETED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=tenant_schema,
            target_entity="LearningPackage",
            target_id=str(package_id),
            metadata={
                "items_created":     len(new_items),
                "unit_number":       unit_number,
                "top_n":             effective_top_n,
                "raw_items_fetched": len(all_raw_items),
                "failed_providers":  failed_providers,
                "ai_model":          ai_model,
                "prompt_hash":       prompt_hash[:16],
            },
        )

        logger.info(
            "m05.curate: complete (items=%d failed_providers=%s)",
            len(new_items), failed_providers or "none",
            extra=_log_extra,
        )

        return {
            "package_id":        str(package_id),
            "items_created":     len(new_items),
            "unit_number":       unit_number,
            "failed_providers":  failed_providers,
        }

    except Exception as exc:
        # Best-effort reset to PENDING so faculty can retry.
        try:
            async with AsyncSession(engine, expire_on_commit=False) as reset_session:
                await reset_session.execute(
                    text(f"SET search_path TO {tenant_schema}, public")
                )
                await LearningPackageRepository.update_status(
                    package_id, PackageStatus.PENDING, db=reset_session
                )
                await reset_session.commit()
        except Exception:
            logger.exception(
                "m05.curate: failed to reset package %s to PENDING after error",
                package_id,
                extra=_log_extra,
            )

        try:
            await AuditService.log(
                AuditEventType.LEARNING_PACKAGE_CURATION_FAILED,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=tenant_schema,
                target_entity="LearningPackage",
                target_id=str(package_id),
                metadata={"error": str(exc)[:500], "unit_number": unit_number},
            )
        except Exception:
            logger.exception(
                "m05.curate: failed to log LEARNING_PACKAGE_CURATION_FAILED audit",
                extra=_log_extra,
            )

        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(raw) -> str | None:
    """SHA-256 of normalized url + title for dedup (R2).

    Returns None if both url and title are empty (should not happen in practice).
    """
    url_part   = (raw.url or "").strip().lower()
    title_part = (raw.title or "").strip().lower()
    if not url_part and not title_part:
        return None
    return hashlib.sha256(f"{url_part}|{title_part}".encode()).hexdigest()
