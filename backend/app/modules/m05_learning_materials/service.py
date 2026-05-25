"""
M05 Learning Material Packager — Package service layer (STEP-11).

Architecture contract (mirrors M03 CourseKitService):
  - All business logic lives here; routers are pure HTTP glue.
  - PackageServiceError carries a machine-readable `code`, human `message`,
    and HTTP `status_code` so routers can raise HTTPException without logic.
  - Curation and RAG indexing are dispatched as separate Celery tasks.
  - Faculty item mutations (add/remove/recommend) are allowed on READY packages.
  - AI advises, humans decide: no autonomous grade, penalty, or rejection logic.
  - Audit logging for AI triggers uses the existing AuditEventType values.
  - TaskJobPublicRepository is imported from M02 (same table, same pattern).

Methods
-------
  dispatch_curation          create PENDING package + dispatch curate task
  dispatch_rag_indexing      dispatch index task for a READY package
  get_package                get by id
  list_packages              paginated list by syllabus (with optional status filter)
  add_faculty_item           append a faculty-added item to a READY package
  remove_item                remove any item from a READY package
  toggle_faculty_recommendation  set/clear the faculty_recommended flag
  ask_question               delegate Q&A to rag_service.ask_package_question
  on_syllabus_version_bump   mark READY packages OUTDATED (R7 hook for M02)
  get_job_status             look up task_jobs row by (job_id, tenant_id)
"""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m05_learning_materials.models import (
    LearningPackage,
    MaterialSourceType,
    PackageItem,
    PackageStatus,
)
from app.modules.m05_learning_materials.repository import (
    LearningPackageRepository,
    PackageItemRepository,
)
from app.modules.m05_learning_materials.schemas import (
    CurationJobResponse,
    FacultyAddItemRequest,
)

logger = logging.getLogger("vidya.service.m05")


# ---------------------------------------------------------------------------
# Exported error class
# ---------------------------------------------------------------------------

class PackageServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal guards
# ---------------------------------------------------------------------------

async def _require_package(
    package_id: UUID,
    *,
    db: AsyncSession,
) -> LearningPackage:
    pkg = await LearningPackageRepository.get_by_id(package_id, db=db)
    if pkg is None:
        raise PackageServiceError("NOT_FOUND", "Learning package not found.", 404)
    return pkg


async def _require_ready(
    package_id: UUID,
    *,
    db: AsyncSession,
) -> LearningPackage:
    pkg = await _require_package(package_id, db=db)
    if pkg.status != PackageStatus.READY:
        raise PackageServiceError(
            "PACKAGE_NOT_READY",
            f"Package is {pkg.status.value}; this operation requires READY status.",
            409,
        )
    return pkg


async def _require_mutable(
    package_id: UUID,
    *,
    db: AsyncSession,
) -> LearningPackage:
    """Looser guard for manual faculty additions: allows PENDING + READY.

    CURATING is blocked to avoid conflicting with an in-flight AI curation task.
    OUTDATED is blocked because the package has been superseded.
    """
    pkg = await _require_package(package_id, db=db)
    if pkg.status == PackageStatus.CURATING:
        raise PackageServiceError(
            "PACKAGE_CURATING",
            "AI curation is in progress — wait for it to complete before adding items.",
            409,
        )
    if pkg.status == PackageStatus.OUTDATED:
        raise PackageServiceError(
            "PACKAGE_OUTDATED",
            "This package is outdated. Re-trigger curation to get a fresh version.",
            409,
        )
    return pkg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(title: str, url: str | None) -> str | None:
    """SHA-256 of normalized url + title (matches curation task R2 algorithm)."""
    url_part   = (url or "").strip().lower()
    title_part = (title or "").strip().lower()
    if not url_part and not title_part:
        return None
    return hashlib.sha256(f"{url_part}|{title_part}".encode()).hexdigest()


# ---------------------------------------------------------------------------
# LearningPackageService
# ---------------------------------------------------------------------------

class LearningPackageService:

    # =========================================================================
    # Curation dispatch
    # =========================================================================

    @staticmethod
    async def dispatch_curation(
        syllabus_id: UUID,
        unit_number: int,
        created_by: UUID,
        tenant_id: UUID,
        tenant_schema: str,
        top_n: int | None = None,
        *,
        db: AsyncSession,
    ) -> CurationJobResponse:
        """Create a PENDING package and dispatch the curation Celery task.

        Rejects with 409 if a curation is already running for this unit.
        Multiple versions (re-curations) are allowed; each creates a new package row.
        """
        from app.modules.m02_syllabus.repository import TaskJobPublicRepository
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        from app.workers.heavy.curate_learning_package import curate_learning_package

        # Block duplicate dispatch while a curation is in flight.
        existing = await LearningPackageRepository.get_by_syllabus_unit(
            syllabus_id, unit_number, db=db
        )
        if existing is not None and existing.status == PackageStatus.CURATING:
            raise PackageServiceError(
                "ALREADY_CURATING",
                f"Curation already running for unit {unit_number} "
                f"(package {existing.id}). Wait for it to complete.",
                409,
            )

        from app.config import settings
        effective_top_n = top_n if top_n is not None else settings.M05_TOP_N_PER_UNIT

        pkg = await LearningPackageRepository.create(
            syllabus_id=syllabus_id,
            unit_number=unit_number,
            created_by_user_id=created_by,
            top_n=effective_top_n,
            db=db,
        )

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="curate_learning_package",
            queue_name="heavy",
            payload={"package_id": str(pkg.id), "tenant_schema": tenant_schema},
            db=db,
        )

        await db.commit()

        curate_learning_package.delay(
            job_id=str(job_id),
            package_id=str(pkg.id),
            tenant_id=str(tenant_id),
            tenant_schema=tenant_schema,
            syllabus_id=str(syllabus_id),
            unit_number=unit_number,
            top_n=effective_top_n,
        )

        await AuditService.log(
            AuditEventType.LEARNING_PACKAGE_CURATION_QUEUED,
            actor_user_id=created_by,
            actor_role="FACULTY",
            tenant_id=tenant_id,
            schema_name=tenant_schema,
            target_entity="LearningPackage",
            target_id=str(pkg.id),
            metadata={
                "syllabus_id": str(syllabus_id),
                "unit_number": unit_number,
                "top_n": effective_top_n,
                "job_id": str(job_id),
            },
        )

        logger.info(
            "m05.service: curation queued (package=%s unit=%s job=%s)",
            pkg.id, unit_number, job_id,
        )

        return CurationJobResponse(
            job_id=job_id,
            package_id=pkg.id,
            status="queued",
        )

    @staticmethod
    async def dispatch_rag_indexing(
        package_id: UUID,
        tenant_id: UUID,
        tenant_schema: str,
        *,
        db: AsyncSession,
    ) -> str:
        """Dispatch the RAG indexing Celery task for a READY package.

        Returns job_id as a string.  Re-indexing is allowed (upsert is idempotent).
        """
        from app.modules.m02_syllabus.repository import TaskJobPublicRepository
        from app.workers.heavy.index_package_rag import index_package_rag

        await _require_ready(package_id, db=db)

        job_id = await TaskJobPublicRepository.create(
            tenant_id=tenant_id,
            task_type="index_package_rag",
            queue_name="heavy",
            payload={"package_id": str(package_id), "tenant_schema": tenant_schema},
            db=db,
        )

        await db.commit()

        index_package_rag.delay(
            job_id=str(job_id),
            package_id=str(package_id),
            tenant_id=str(tenant_id),
            tenant_schema=tenant_schema,
        )

        logger.info(
            "m05.service: RAG indexing queued (package=%s job=%s)", package_id, job_id
        )

        return str(job_id)

    # =========================================================================
    # Read
    # =========================================================================

    @staticmethod
    async def get_package(
        package_id: UUID,
        *,
        db: AsyncSession,
    ) -> LearningPackage | None:
        return await LearningPackageRepository.get_by_id(package_id, db=db)

    @staticmethod
    async def list_packages(
        syllabus_id: UUID | None,
        *,
        status_filter: PackageStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> tuple[int, list[LearningPackage]]:
        offset = (page - 1) * page_size
        if syllabus_id is not None:
            total = await LearningPackageRepository.count_by_syllabus(
                syllabus_id, status_filter=status_filter, db=db
            )
            items = await LearningPackageRepository.list_by_syllabus(
                syllabus_id,
                status_filter=status_filter,
                offset=offset,
                limit=page_size,
                db=db,
            )
        else:
            total = await LearningPackageRepository.count_all(status_filter=status_filter, db=db)
            items = await LearningPackageRepository.list_all(
                status_filter=status_filter, offset=offset, limit=page_size, db=db
            )
        return total, items

    @staticmethod
    async def list_items(
        package_id: UUID,
        *,
        faculty_only: bool = False,
        db: AsyncSession,
    ) -> list[PackageItem]:
        """Return items for a package ordered by display_order."""
        return await PackageItemRepository.list_by_package(
            package_id, faculty_only=faculty_only, db=db
        )

    # =========================================================================
    # Faculty item management
    # =========================================================================

    @staticmethod
    async def add_faculty_item(
        package_id: UUID,
        payload: FacultyAddItemRequest,
        added_by: UUID,
        *,
        db: AsyncSession,
    ) -> PackageItem:
        """Append a faculty-supplied item to a PENDING or READY package.

        CURATING and OUTDATED packages are blocked to avoid race conditions
        with an in-flight AI task or a superseded package version.
        Deduplicates by content_hash — raises DUPLICATE_ITEM if already present.
        New item is appended at the end (display_order = current item_count).
        item_count is incremented after successful insert.
        """
        pkg = await _require_mutable(package_id, db=db)

        content_hash = _content_hash(payload.title, payload.url)
        if content_hash is not None:
            if await PackageItemRepository.dedup_hash_exists(
                package_id, content_hash, db=db
            ):
                raise PackageServiceError(
                    "DUPLICATE_ITEM",
                    "An item with the same title/URL is already in this package.",
                    409,
                )

        display_order = pkg.item_count
        meta = payload.metadata.model_dump(exclude_none=True)

        items = await PackageItemRepository.bulk_create(
            package_id,
            [
                {
                    "source_type":         payload.source_type,
                    "title":               payload.title,
                    "url":                 payload.url,
                    "content_hash":        content_hash,
                    "metadata":            meta,
                    "relevance_score":     None,
                    "display_order":       display_order,
                    "faculty_recommended": True,
                    "added_by_user_id":    added_by,
                }
            ],
            db=db,
        )

        await LearningPackageRepository.update_item_count(
            package_id, pkg.item_count + 1, db=db
        )
        await db.commit()

        logger.info(
            "m05.service: faculty item added (package=%s item=%s)",
            package_id, items[0].id,
        )
        return items[0]

    @staticmethod
    async def remove_item(
        package_id: UUID,
        item_id: UUID,
        *,
        db: AsyncSession,
    ) -> None:
        """Remove any item from a READY package and decrement item_count."""
        pkg = await _require_ready(package_id, db=db)

        item = await PackageItemRepository.get_by_id(item_id, db=db)
        if item is None or item.package_id != package_id:
            raise PackageServiceError("NOT_FOUND", "Package item not found.", 404)

        from sqlalchemy import delete as sa_delete
        from app.modules.m05_learning_materials.models import PackageItem as _PackageItem
        from sqlalchemy import text as sa_text

        await db.execute(
            sa_delete(_PackageItem).where(_PackageItem.id == item_id)
        )
        new_count = max(0, pkg.item_count - 1)
        await LearningPackageRepository.update_item_count(
            package_id, new_count, db=db
        )
        await db.commit()

        logger.info(
            "m05.service: item removed (package=%s item=%s)", package_id, item_id
        )

    @staticmethod
    async def toggle_faculty_recommendation(
        package_id: UUID,
        item_id: UUID,
        value: bool,
        *,
        db: AsyncSession,
    ) -> PackageItem:
        """Set or clear the faculty_recommended flag on an item."""
        await _require_ready(package_id, db=db)

        item = await PackageItemRepository.get_by_id(item_id, db=db)
        if item is None or item.package_id != package_id:
            raise PackageServiceError("NOT_FOUND", "Package item not found.", 404)

        updated = await PackageItemRepository.set_faculty_recommended(
            item_id, value, db=db
        )
        if updated is None:
            raise PackageServiceError("NOT_FOUND", "Package item not found.", 404)

        await db.commit()
        return updated

    # =========================================================================
    # Q&A session reads
    # =========================================================================

    @staticmethod
    async def list_qa_sessions(
        package_id: UUID,
        student_user_id: UUID,
        *,
        db: AsyncSession,
    ) -> list:
        from app.modules.m05_learning_materials.repository import PackageQARepository

        return await PackageQARepository.list_sessions_for_student(
            package_id, student_user_id, db=db
        )

    @staticmethod
    async def get_qa_session(
        session_id: UUID,
        *,
        db: AsyncSession,
    ):
        from app.modules.m05_learning_materials.repository import PackageQARepository

        return await PackageQARepository.get_session_with_messages(session_id, db=db)

    # =========================================================================
    # Q&A
    # =========================================================================

    @staticmethod
    async def ask_question(
        package_id: UUID,
        student_user_id: UUID,
        question: str,
        tenant_schema: str,
        session_id: UUID | None,
        *,
        db: AsyncSession,
    ) -> dict:
        """Delegate to rag_service.ask_package_question.

        Package must be READY and qdrant_indexed.
        """
        pkg = await _require_ready(package_id, db=db)
        if not pkg.qdrant_indexed:
            raise PackageServiceError(
                "NOT_INDEXED",
                "Package has not been RAG-indexed yet. "
                "Trigger indexing first via dispatch_rag_indexing.",
                409,
            )

        from app.modules.m05_learning_materials.rag_service import (
            ask_package_question,
            RagAIError,
            RagServiceError,
        )

        try:
            return await ask_package_question(
                package_id=package_id,
                student_user_id=student_user_id,
                question=question,
                tenant_schema=tenant_schema,
                session_id=session_id,
                db=db,
            )
        except RagAIError as exc:
            raise PackageServiceError("AI_ERROR", str(exc), 503)
        except RagServiceError as exc:
            raise PackageServiceError("RAG_ERROR", str(exc), 503)

    # =========================================================================
    # Syllabus-bump hook (R7)
    # =========================================================================

    @staticmethod
    async def on_syllabus_version_bump(
        syllabus_id: UUID,
        *,
        db: AsyncSession,
    ) -> int:
        """Mark all READY packages for this syllabus as OUTDATED.

        Called by the M02 syllabus service when a new syllabus version is approved.
        Returns the number of packages transitioned.
        Faculty or admin should then trigger dispatch_curation for affected units.
        """
        count = await LearningPackageRepository.mark_outdated_by_syllabus(
            syllabus_id, db=db
        )
        await db.commit()

        logger.info(
            "m05.service: %d package(s) marked OUTDATED for syllabus %s",
            count, syllabus_id,
        )
        return count

    # =========================================================================
    # Job status
    # =========================================================================

    @staticmethod
    async def get_job_status(
        job_id: UUID,
        tenant_id: UUID,
        *,
        db: AsyncSession,
    ) -> dict | None:
        from app.modules.m02_syllabus.repository import TaskJobPublicRepository

        return await TaskJobPublicRepository.get_by_id(job_id, tenant_id, db=db)
