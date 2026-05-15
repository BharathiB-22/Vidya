"""
Celery heavy-queue task: index curated learning package items into Qdrant (STEP-09).

Flow
----
  1. Ensure Qdrant collection m05_rag exists (create with 768-dim cosine if absent).
  2. Load all package items via PackageItemRepository.list_by_package().
  3. For each item:
     a. Build index text from title + abstract_snippet in metadata.
     b. Chunk text using M05_RAG_CHUNK_TOKENS / M05_RAG_CHUNK_OVERLAP settings.
     c. Embed all chunks via embed_texts().
     d. Upsert chunk vectors into Qdrant with tenant-safe payload.
     e. Mark item.qdrant_indexed = True via PackageItemRepository.set_qdrant_indexed().
     f. Per-item failures: log warning + continue (do not abort the package).
  4. Mark package.qdrant_indexed = True via LearningPackageRepository.set_qdrant_indexed().
  5. Commit, then audit LEARNING_PACKAGE_RAG_INDEXING_COMPLETED.

On failure:
  - qdrant_indexed remains False on affected rows.
  - Qdrant upsert is idempotent (uuid5-based point IDs); re-runs are safe.
  - Audit LEARNING_PACKAGE_RAG_INDEXING_FAILED.
  - Re-raise so Celery marks the task FAILED.

Chunking
--------
  Token approximation: 4 chars per token.
  Point ID = uuid5(NAMESPACE_URL, "{item_id}:{chunk_index}") — deterministic across retries.

Qdrant collection strategy
--------------------------
  Single shared collection "m05_rag" with payload-based filtering.
  tenant_schema + package_id are mandatory payload fields on every point (R1).
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from uuid import UUID

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m05.index_package_rag")

_QDRANT_COLLECTION = "m05_rag"
_EMBED_DIM = 768  # text-embedding-004 default output dimension

_async_engine = None
_qdrant_client = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


def _get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import AsyncQdrantClient
        from app.config import settings
        kwargs: dict = {"url": settings.QDRANT_URL}
        if settings.QDRANT_API_KEY:
            kwargs["api_key"] = settings.QDRANT_API_KEY
        _qdrant_client = AsyncQdrantClient(**kwargs)
    return _qdrant_client


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.index_package_rag",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def index_package_rag(
    *,
    job_id: str,
    package_id: str,
    tenant_id: str,
    tenant_schema: str,
    request_id: str | None = None,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_indexing(
            package_id=UUID(package_id),
            tenant_id=UUID(tenant_id),
            tenant_schema=tenant_schema,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_indexing(
    package_id: UUID,
    tenant_id: UUID,
    tenant_schema: str,
) -> dict:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from qdrant_client.models import PointStruct

    from app.config import settings
    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m05_learning_materials.embedder import EmbedderError, embed_texts
    from app.modules.m05_learning_materials.repository import (
        LearningPackageRepository,
        PackageItemRepository,
    )

    _log_extra = {
        "tenant_schema": tenant_schema,
        "package_id": str(package_id),
    }

    engine = _get_async_engine()
    qdrant = _get_qdrant_client()

    indexed_count = 0
    failed_count = 0
    total_vectors = 0

    try:
        # ------------------------------------------------------------------
        # 1. Ensure Qdrant collection exists
        # ------------------------------------------------------------------
        await _ensure_collection(qdrant)

        # ------------------------------------------------------------------
        # 2. Load items + index within a single DB session
        # ------------------------------------------------------------------
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(
                text(f"SET search_path TO {tenant_schema}, public")
            )

            items = await PackageItemRepository.list_by_package(
                package_id, db=session
            )
            logger.info(
                "m05.index_rag: loaded %d item(s) to index",
                len(items),
                extra=_log_extra,
            )

            # ------------------------------------------------------------------
            # 3. Index each item; tolerate per-item failures
            # ------------------------------------------------------------------
            for item in items:
                _item_extra = {**_log_extra, "item_id": str(item.id)}
                try:
                    index_text = _build_index_text(item)
                    chunks = _chunk_text(
                        index_text,
                        settings.M05_RAG_CHUNK_TOKENS,
                        settings.M05_RAG_CHUNK_OVERLAP,
                    )

                    vectors = await embed_texts(
                        chunks,
                        tenant_schema=tenant_schema,
                        package_id=str(package_id),
                    )

                    source_type_str = (
                        item.source_type.value
                        if hasattr(item.source_type, "value")
                        else str(item.source_type)
                    )

                    points = [
                        PointStruct(
                            id=str(_chunk_point_id(item.id, chunk_idx)),
                            vector=vector,
                            payload={
                                "tenant_schema": tenant_schema,
                                "package_id": str(package_id),
                                "item_id": str(item.id),
                                "source_type": source_type_str,
                                "title": item.title,
                                "url": item.url,
                                "chunk_index": chunk_idx,
                                "total_chunks": len(chunks),
                                "text_snippet": chunks[chunk_idx][:200],
                            },
                        )
                        for chunk_idx, vector in enumerate(vectors)
                    ]

                    await qdrant.upsert(
                        collection_name=_QDRANT_COLLECTION,
                        points=points,
                    )
                    total_vectors += len(points)

                    await PackageItemRepository.set_qdrant_indexed(
                        item.id, db=session
                    )
                    indexed_count += 1
                    logger.info(
                        "m05.index_rag: item indexed (%d chunk(s))",
                        len(chunks),
                        extra=_item_extra,
                    )

                except Exception as exc:
                    failed_count += 1
                    logger.warning(
                        "m05.index_rag: item %s failed (%s); skipping",
                        item.id, exc,
                        extra=_item_extra,
                    )

            # ------------------------------------------------------------------
            # 4. Mark package as Qdrant-indexed
            # ------------------------------------------------------------------
            await LearningPackageRepository.set_qdrant_indexed(
                package_id, db=session
            )

            await session.commit()

        # ------------------------------------------------------------------
        # 5. Audit
        # ------------------------------------------------------------------
        await AuditService.log(
            AuditEventType.LEARNING_PACKAGE_RAG_INDEXING_COMPLETED,
            actor_role="SYSTEM",
            tenant_id=tenant_id,
            schema_name=tenant_schema,
            target_entity="LearningPackage",
            target_id=str(package_id),
            metadata={
                "indexed_count": indexed_count,
                "failed_count": failed_count,
                "total_vectors": total_vectors,
            },
        )

        logger.info(
            "m05.index_rag: complete (indexed=%d failed=%d vectors=%d)",
            indexed_count, failed_count, total_vectors,
            extra=_log_extra,
        )

        return {
            "package_id": str(package_id),
            "indexed_count": indexed_count,
            "failed_count": failed_count,
            "total_vectors": total_vectors,
        }

    except Exception as exc:
        try:
            await AuditService.log(
                AuditEventType.LEARNING_PACKAGE_RAG_INDEXING_FAILED,
                actor_role="SYSTEM",
                tenant_id=tenant_id,
                schema_name=tenant_schema,
                target_entity="LearningPackage",
                target_id=str(package_id),
                metadata={"error": str(exc)[:500]},
            )
        except Exception:
            logger.exception(
                "m05.index_rag: failed to log RAG_INDEXING_FAILED audit",
                extra=_log_extra,
            )
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ensure_collection(qdrant) -> None:
    """Create m05_rag Qdrant collection if it does not exist."""
    from qdrant_client.models import Distance, VectorParams

    try:
        result = await qdrant.get_collections()
        existing = {c.name for c in result.collections}
        if _QDRANT_COLLECTION not in existing:
            await qdrant.create_collection(
                collection_name=_QDRANT_COLLECTION,
                vectors_config=VectorParams(size=_EMBED_DIM, distance=Distance.COSINE),
            )
            logger.info(
                "m05.index_rag: created Qdrant collection %r", _QDRANT_COLLECTION
            )
    except Exception as exc:
        raise RuntimeError(
            f"Qdrant collection setup failed for {_QDRANT_COLLECTION!r}: {exc}"
        ) from exc


def _build_index_text(item) -> str:
    """Build searchable text from stored PackageItem fields.

    raw_text is not persisted in the DB; reconstruct from title + abstract_snippet.
    """
    meta = item.metadata_ or {}
    parts = [item.title]
    snippet = meta.get("abstract_snippet") or ""
    if snippet:
        parts.append(str(snippet))
    return " ".join(parts)


def _chunk_text(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text into overlapping chunks. Approximates tokens at 4 chars each.

    Returns a list of at least one chunk. Chunk ordering is deterministic.
    stride is clamped to >= 1 to prevent infinite loops when overlap >= chunk_size.
    """
    chunk_chars = chunk_tokens * 4
    overlap_chars = overlap_tokens * 4
    if len(text) <= chunk_chars:
        return [text]
    stride = max(1, chunk_chars - overlap_chars)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_chars])
        if start + chunk_chars >= len(text):
            break
        start += stride
    return chunks


def _chunk_point_id(item_id: UUID, chunk_index: int) -> uuid.UUID:
    """Deterministic Qdrant point ID: uuid5(NAMESPACE_URL, '{item_id}:{chunk_index}').

    Stable across Celery retries — upsert is idempotent.
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{item_id}:{chunk_index}")
