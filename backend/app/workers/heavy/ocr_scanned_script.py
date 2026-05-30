"""
Celery heavy-queue task: extract OCR text from a scanned answer script (M09 H-36 STEP-03).

Flow:
  1. Load ScannedScript from DB (expected status: OCR_PROCESSING).
  2. Set ocr_status → "PROCESSING". Audit SCRIPT_OCR_STARTED.
  3. Download PDF bytes from S3 using script.upload_url.
  4. Extract text using _extract_text_from_pdf (pypdf built-in text layer extraction).
     This is best-effort: works for text-based PDFs; returns empty for scanned image PDFs.
  5a. Text found (len >= OCR_MIN_CHARS):
       ocr_status = "COMPLETE", ocr_text = <extracted>, status → PROCESSING.
       Dispatch score_scanned_script to continue the pipeline.
  5b. Text empty / too short:
       ocr_status = "EMPTY", ocr_text = None, status → REVIEW_REQUIRED.
       Evaluator must enter marks manually.
  6. Commit. Audit SCRIPT_OCR_COMPLETED or SCRIPT_OCR_FAILED.

On unrecoverable exception:
  - ocr_status = "FAILED", status → FAILED.
  - Audit SCRIPT_OCR_FAILED.
  - Re-raise so Celery marks the task FAILED.

Human-gate invariants:
  - This task NEVER sets status beyond PROCESSING.
  - evaluator_marks is NEVER written by this task.
  - exam_score_ledger is NEVER written by this task.
  - student_user_id is NEVER logged or exposed by this task.

OCR implementation note:
  pypdf.extract_text() works only for PDFs with embedded text layers.
  Actual handwritten/printed scanned scripts (raster images inside PDF)
  will return empty — those go to REVIEW_REQUIRED for manual evaluation.
  A future sprint will integrate Tesseract or Google Vision for true OCR.
"""
import asyncio
import logging
import sys

from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m09.ocr_scanned_script")

# Scripts with extracted text shorter than this are treated as empty (no usable OCR).
OCR_MIN_CHARS = 50

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _async_engine


def _s3_get_object(object_key: str) -> bytes:
    """Download an S3 object and return its raw bytes."""
    import boto3
    from app.config import settings

    client = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=getattr(settings, "S3_REGION", "us-east-1"),
        use_ssl=getattr(settings, "S3_USE_SSL", False),
    )
    bucket = settings.S3_BUCKET
    key = object_key.removeprefix(f"{bucket}/")
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def _extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    """
    Extract text from a PDF using pypdf's built-in text-layer extraction.

    Returns (combined_text, page_count).
    combined_text is empty string when the PDF contains only raster images
    (typical for scanned answer scripts).
    """
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    texts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
            texts.append(page_text)
        except Exception as exc:
            logger.debug("Text extraction failed for page: %s", exc)
            texts.append("")
    combined = "\n".join(texts).strip()
    return combined, len(reader.pages)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.ocr_scanned_script",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def ocr_scanned_script(
    *,
    job_id: str,
    script_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(
        _run_ocr(
            script_id=script_id,
            schema_name=schema_name,
        )
    )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_ocr(*, script_id: str, schema_name: str) -> dict:
    import uuid
    from uuid import UUID
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m09_paper_admin.models import ScriptStatus
    from app.modules.m09_paper_admin.repository import ScriptRepository

    engine = _get_async_engine()
    script_uuid = UUID(script_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET search_path TO {schema_name}, public"))

        # 1. Load script
        script = await ScriptRepository.get_by_id(script_uuid, db=session)
        if script is None:
            raise ValueError(
                f"ScannedScript {script_id} not found in schema {schema_name!r}."
            )

        # 2. Mark OCR in progress
        await ScriptRepository.set_ocr_processing(script_uuid, db=session)
        await session.commit()

        await AuditService.log(
            AuditEventType.SCRIPT_OCR_STARTED,
            actor_user_id=None,
            actor_role="SYSTEM",
            tenant_id=None,
            schema_name=schema_name,
            target_entity="scanned_script",
            target_id=script_id,
            metadata={"upload_url": script.upload_url},
        )

        try:
            # 3. Download PDF from S3
            if script.upload_url:
                try:
                    pdf_bytes = _s3_get_object(script.upload_url)
                except Exception as s3_exc:
                    logger.warning(
                        "S3 download failed for script=%s key=%s: %s",
                        script_id, script.upload_url, s3_exc,
                    )
                    pdf_bytes = b""
            else:
                logger.warning(
                    "script=%s has no upload_url — OCR will produce empty result.",
                    script_id,
                )
                pdf_bytes = b""

            # 4. Extract text
            if pdf_bytes:
                extracted_text, page_count = _extract_text_from_pdf(pdf_bytes)
            else:
                extracted_text, page_count = "", 0

            had_ocr     = len(extracted_text) >= OCR_MIN_CHARS
            ocr_status_val = "COMPLETE" if had_ocr else "EMPTY"
            ocr_text_val   = extracted_text if had_ocr else None

            # 5. Save OCR result + advance status
            await ScriptRepository.set_ocr_result(
                script_uuid,
                ocr_text=ocr_text_val,
                ocr_status_value=ocr_status_val,
                had_ocr=had_ocr,
                db=session,
            )
            await session.commit()

            new_status = (
                ScriptStatus.PROCESSING.value
                if had_ocr
                else ScriptStatus.REVIEW_REQUIRED.value
            )

            # 5a. Chain to scoring task when text is available
            if had_ocr:
                from app.workers.heavy.score_scanned_script import score_scanned_script
                score_scanned_script.apply_async(
                    kwargs={
                        "job_id":      str(uuid.uuid4()),
                        "script_id":   script_id,
                        "schema_name": schema_name,
                    },
                    queue="celery-heavy",
                )
                logger.info(
                    "score_scanned_script dispatched for script=%s (OCR text: %d chars)",
                    script_id, len(extracted_text),
                )

            # 6. Audit
            await AuditService.log(
                AuditEventType.SCRIPT_OCR_COMPLETED,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="scanned_script",
                target_id=script_id,
                metadata={
                    "had_ocr":        had_ocr,
                    "ocr_status":     ocr_status_val,
                    "text_length":    len(extracted_text),
                    "page_count":     page_count,
                    "final_status":   new_status,
                },
            )

            logger.info(
                "OCR complete: script=%s had_ocr=%s text_len=%d status=%s",
                script_id, had_ocr, len(extracted_text), new_status,
            )

            return {
                "script_id":  script_id,
                "had_ocr":    had_ocr,
                "ocr_status": ocr_status_val,
                "text_length": len(extracted_text),
                "status":     new_status,
            }

        except Exception as exc:
            logger.error(
                "OCR failed for script=%s: %s", script_id, exc, exc_info=True,
            )
            try:
                await ScriptRepository.set_failed(script_uuid, db=session)
                await session.execute(
                    text(
                        "UPDATE scanned_scripts SET ocr_status = 'FAILED' "
                        "WHERE id = :sid"
                    ),
                    {"sid": script_uuid},
                )
                await session.commit()
            except Exception:
                pass
            try:
                await AuditService.log(
                    AuditEventType.SCRIPT_OCR_FAILED,
                    actor_user_id=None,
                    actor_role="SYSTEM",
                    tenant_id=None,
                    schema_name=schema_name,
                    target_entity="scanned_script",
                    target_id=script_id,
                    metadata={"error": str(exc)[:500]},
                )
            except Exception:
                pass
            raise
