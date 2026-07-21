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

import asyncio
import hashlib
import io
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


def _extract_text(file_bytes: bytes, content_type: str) -> str:
    """Extract plain text from PDF, TXT, or DOCX bytes.

    Returns an empty string on any extraction failure (caller raises EMPTY_CONTENT).
    """
    if content_type == "text/plain":
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="replace")

    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            parts: list[str] = []
            for page in reader.pages:
                text = page.extract_text() or ""
                text = text.strip()
                if text:
                    parts.append(text)
            return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("m05.service: PDF text extraction failed: %s", exc)
            return ""

    if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paras)
        except Exception as exc:
            logger.warning("m05.service: DOCX text extraction failed: %s", exc)
            return ""

    return ""


async def _upload_note_to_s3(
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    tenant_slug: str,
    package_id: UUID,
) -> str:
    """Upload faculty note file to S3/MinIO. Returns the object key.

    Uses asyncio.to_thread so the blocking boto3 call does not stall the event loop.
    Raises on S3 error — caller decides whether to propagate or swallow.
    """
    import uuid as _uuid
    import boto3
    from app.config import settings

    safe_name = filename.replace("/", "_").replace("\\", "_")
    file_uuid = _uuid.uuid4()
    object_key = (
        f"vidya-assets/{tenant_slug}/faculty_notes/{package_id}"
        f"/{file_uuid}-{safe_name}"
    )

    def _put() -> str:
        client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_USE_SSL,
        )
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=object_key,
            Body=file_bytes,
            ContentType=content_type,
        )
        return object_key

    return await asyncio.to_thread(_put)


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
        """Upsert the package for this (syllabus_id, unit_number, version) and
        dispatch the curation Celery task.

        Rejects with 409 if a curation is already running for this unit.
        A non-OUTDATED package for the same syllabus unit is reused (re-curated
        in place) rather than creating a duplicate row — each syllabus + unit +
        version has exactly one LearningPackage. Only a syllabus version bump
        (handled by on_syllabus_version_bump) marks the old package OUTDATED
        and starts a new versioned one.
        """
        from app.modules.m02_syllabus.repository import TaskJobPublicRepository
        from app.core.audit_log.models import AuditEventType
        from app.core.audit_log.service import AuditService
        from app.workers.heavy.curate_learning_package import curate_learning_package

        # Reuse the current (non-OUTDATED) package for this syllabus unit, if any.
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

        if existing is not None:
            # Re-curate in place — reset to PENDING so the worker's precondition
            # passes; curate_learning_package already deletes stale AI items
            # idempotently before rebuilding, so this is safe to repeat.
            pkg = await LearningPackageRepository.reset_for_recuration(
                existing.id, effective_top_n, db=db
            )
        else:
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
    async def _faculty_can_see_syllabus(
        syllabus_id: UUID, faculty_user_id: UUID, *, db: AsyncSession
    ) -> bool:
        """A faculty may see a package only for a course they teach. Resolves the
        package's syllabus to its course, then reuses the shared ownership guard."""
        from app.modules.m02_syllabus.repository import SyllabusRepository
        from app.modules.m_academics.faculty_scope import faculty_teaches_course

        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            return False
        return await faculty_teaches_course(faculty_user_id, syllabus.course_id, db)

    @staticmethod
    async def get_package(
        package_id: UUID,
        *,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> LearningPackage | None:
        pkg = await LearningPackageRepository.get_by_id(package_id, db=db)
        if pkg is None:
            return None
        if caller_role == "DEAN" and caller_user_id is not None:
            if not await LearningPackageService._dean_can_see_syllabus(
                pkg.syllabus_id, caller_user_id, db=db
            ):
                return None
        # A faculty sees a package only for a course they teach — without this,
        # every colleague's materials are one guessable id away.
        if caller_role == "FACULTY" and caller_user_id is not None:
            if not await LearningPackageService._faculty_can_see_syllabus(
                pkg.syllabus_id, caller_user_id, db=db
            ):
                return None
        return pkg

    @staticmethod
    async def _dean_can_see_syllabus(
        syllabus_id: UUID, dean_user_id: UUID, *, db: AsyncSession
    ) -> bool:
        from sqlalchemy import select
        from app.modules.m01_program_advisor.models import Course, Program
        from app.modules.m02_syllabus.repository import SyllabusRepository
        from app.modules.m_academics.dean_scope import get_dean_program_ids

        governed = await get_dean_program_ids(dean_user_id, "DEAN", db)
        if governed is None:
            return True
        syllabus = await SyllabusRepository.get_by_id(syllabus_id, db=db)
        if syllabus is None:
            return False
        result = await db.execute(
            select(Program.acad_program_id)
            .join(Course, Course.program_id == Program.id)
            .where(Course.id == syllabus.course_id)
        )
        acad_program_id = result.scalar_one_or_none()
        return acad_program_id is not None and acad_program_id in governed

    @staticmethod
    async def list_packages(
        syllabus_id: UUID | None,
        *,
        status_filter: PackageStatus | None = None,
        page: int = 1,
        page_size: int = 50,
        caller_role: str | None = None,
        caller_user_id: UUID | None = None,
        db: AsyncSession,
    ) -> tuple[int, list[LearningPackage]]:
        offset = (page - 1) * page_size

        if caller_role == "DEAN" and caller_user_id is not None:
            from sqlalchemy import select
            from app.modules.m01_program_advisor.models import Course, Program
            from app.modules.m02_syllabus.models import Syllabus
            from app.modules.m_academics.dean_scope import get_dean_program_ids

            governed = await get_dean_program_ids(caller_user_id, "DEAN", db)
            if governed is not None:
                if syllabus_id is not None:
                    if not await LearningPackageService._dean_can_see_syllabus(
                        syllabus_id, caller_user_id, db=db
                    ):
                        return 0, []
                else:
                    course_subq = (
                        select(Course.id)
                        .join(Program, Program.id == Course.program_id)
                        .where(Program.acad_program_id.in_(governed))
                    )
                    governed_syllabus_ids = list(
                        (
                            await db.execute(
                                select(Syllabus.id).where(Syllabus.course_id.in_(course_subq))
                            )
                        ).scalars().all()
                    )
                    total = await LearningPackageRepository.count_by_syllabus_ids(
                        governed_syllabus_ids, status_filter=status_filter, db=db
                    )
                    items = await LearningPackageRepository.list_by_syllabus_ids(
                        governed_syllabus_ids,
                        status_filter=status_filter,
                        offset=offset,
                        limit=page_size,
                        db=db,
                    )
                    return total, items

        # A faculty sees only packages for courses they teach. Mirrors the DEAN
        # branch above, scoped by assignment instead of governed programme.
        if caller_role == "FACULTY" and caller_user_id is not None:
            from sqlalchemy import select
            from app.modules.m02_syllabus.models import Syllabus
            from app.modules.m_academics.assignment_repository import SubjectAssignmentRepository

            if syllabus_id is not None:
                if not await LearningPackageService._faculty_can_see_syllabus(
                    syllabus_id, caller_user_id, db=db
                ):
                    return 0, []
            else:
                assignments = await SubjectAssignmentRepository.list_by_faculty(
                    caller_user_id, db=db
                )
                course_ids = list({a.course_id for a in assignments})
                if not course_ids:
                    return 0, []
                taught_syllabus_ids = list(
                    (await db.execute(
                        select(Syllabus.id).where(Syllabus.course_id.in_(course_ids))
                    )).scalars().all()
                )
                total = await LearningPackageRepository.count_by_syllabus_ids(
                    taught_syllabus_ids, status_filter=status_filter, db=db
                )
                items = await LearningPackageRepository.list_by_syllabus_ids(
                    taught_syllabus_ids,
                    status_filter=status_filter, offset=offset, limit=page_size, db=db,
                )
                return total, items

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
    # Faculty note upload (PDF / TXT / DOCX)
    # =========================================================================

    @staticmethod
    async def ingest_faculty_note(
        package_id: UUID,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        title: str | None,
        added_by: UUID,
        tenant_slug: str,
        *,
        tenant_id: UUID | None = None,
        tenant_schema: str | None = None,
        db: AsyncSession,
    ) -> PackageItem:
        """Extract text from an uploaded PDF/TXT/DOCX and add as a FACULTY_NOTE item.

        Flow:
          1. Validate content_type and file size.
          2. Extract text (pypdf / python-docx / UTF-8 decode).
          3. Upload raw file to S3 (non-blocking; failure is logged, not raised).
          4. Dedup by content_hash (title-based for notes).
          5. Bulk-create one PackageItem with extracted_text in metadata_.
          6. Increment item_count on the parent package.
          7. If the package is READY, immediately (re)dispatch RAG indexing so
             the new note is searchable without a separate manual trigger
             (best-effort — a failure here does not fail the upload).
        """
        _ALLOWED = {
            "application/pdf",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        _EXT_TO_TYPE = {
            "pdf":  "application/pdf",
            "txt":  "text/plain",
            "text": "text/plain",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        # Strip charset/parameters (e.g. "text/plain; charset=utf-8") before matching.
        content_type = (content_type or "").split(";", 1)[0].strip().lower()

        # Some browsers/clients send a generic or missing content-type for
        # otherwise-valid files; fall back to the filename extension so a
        # correctly-named PDF/TXT/DOCX isn't rejected on that basis alone.
        if content_type not in _ALLOWED:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            content_type = _EXT_TO_TYPE.get(ext, content_type)

        if content_type not in _ALLOWED:
            raise PackageServiceError(
                "UNSUPPORTED_FILE_TYPE",
                f"Content type {content_type!r} is not supported. "
                "Please upload a PDF, plain-text, or DOCX file.",
                415,
            )

        _MAX_BYTES = 20 * 1024 * 1024  # 20 MB
        if len(file_bytes) > _MAX_BYTES:
            raise PackageServiceError("FILE_TOO_LARGE", "File exceeds the 20 MB limit.", 413)

        pkg = await _require_mutable(package_id, db=db)

        display_title = (title or "").strip() or filename.rsplit(".", 1)[0]

        extracted_text = _extract_text(file_bytes, content_type)
        if not extracted_text.strip():
            raise PackageServiceError(
                "EMPTY_CONTENT",
                "No readable text could be extracted from the uploaded file. "
                "Verify the file is not empty or password-protected.",
                422,
            )

        # S3 upload — best-effort; a failure does not block item creation
        storage_key: str | None = None
        try:
            storage_key = await _upload_note_to_s3(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
                tenant_slug=tenant_slug,
                package_id=package_id,
            )
        except Exception as exc:
            logger.warning(
                "m05.service: S3 upload failed for faculty note (package=%s file=%r): %s",
                package_id, filename, exc,
            )

        content_hash = _content_hash(display_title, None)
        if content_hash is not None:
            if await PackageItemRepository.dedup_hash_exists(package_id, content_hash, db=db):
                raise PackageServiceError(
                    "DUPLICATE_ITEM",
                    "A faculty note with the same title already exists in this package.",
                    409,
                )

        word_count = len(extracted_text.split())
        meta: dict = {
            "original_filename": filename,
            "content_type": content_type,
            "extracted_text": extracted_text,
            "word_count": word_count,
        }
        if storage_key:
            meta["storage_key"] = storage_key

        display_order = pkg.item_count
        items = await PackageItemRepository.bulk_create(
            package_id,
            [{
                "source_type":         MaterialSourceType.FACULTY_NOTE,
                "title":               display_title,
                "url":                 None,
                "content_hash":        content_hash,
                "metadata":            meta,
                "relevance_score":     None,
                "display_order":       display_order,
                "faculty_recommended": True,
                "added_by_user_id":    added_by,
            }],
            db=db,
        )

        await LearningPackageRepository.update_item_count(
            package_id, pkg.item_count + 1, db=db
        )
        await db.commit()

        logger.info(
            "m05.service: faculty note ingested (package=%s item=%s words=%d file=%r)",
            package_id, items[0].id, word_count, filename,
        )

        # Best-effort: re-index immediately so the note is searchable right away.
        # Only meaningful once the package has already been curated (READY);
        # a PENDING/CURATING package will be indexed by its normal pipeline.
        if pkg.status == PackageStatus.READY and tenant_id is not None and tenant_schema:
            try:
                await LearningPackageService.dispatch_rag_indexing(
                    package_id, tenant_id, tenant_schema, db=db
                )
            except Exception as exc:
                logger.warning(
                    "m05.service: auto re-index after faculty note upload failed "
                    "(package=%s): %s", package_id, exc,
                )

        return items[0]

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
