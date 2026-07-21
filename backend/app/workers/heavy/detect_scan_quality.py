"""
Celery heavy-queue task: detect scan quality for a scanned answer script (M09 H-36 STEP-02).

Flow:
  1. Load ScannedScript from DB.
  2. Set status → QUALITY_CHECKING. Audit SCRIPT_QUALITY_CHECK_STARTED.
  3. Download PDF bytes from S3 using script.upload_url as object key.
     If upload_url is None or S3 download fails, pdf_bytes = b"" (detector flags PARTIAL_SCAN).
  4. Call scan_quality_detector.detect_scan_quality(pdf_bytes, expected_page_count).
  5. Write ocr_quality_score + scan_quality_flags to scanned_scripts.
  6a. passed=True  → status = OCR_PROCESSING  (STEP-03 OCR task takes over).
  6b. passed=False → status = QUALITY_FAILED  (admin must re-upload or override).
  7. Commit. Audit SCRIPT_QUALITY_CHECK_COMPLETED or SCRIPT_QUALITY_CHECK_FAILED.

On unrecoverable exception:
  - Set status → FAILED.
  - Audit SCRIPT_QUALITY_CHECK_FAILED.
  - Re-raise so Celery marks the task FAILED.

Human-gate invariants:
  - This task NEVER sets status beyond OCR_PROCESSING.
  - evaluator_marks is NEVER written by this task.
  - exam_score_ledger is NEVER written by this task.
  - student_user_id is NEVER logged or exposed by this task.
"""
import asyncio
import logging
import sys

from app.database import tenant_schema_scope
from app.workers.base_task import VidyaTask
from app.workers.celery_app import celery_app

logger = logging.getLogger("vidya.worker.m09.detect_scan_quality")

_async_engine = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings
        _async_engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        # Re-apply the schema at the START OF EVERY TRANSACTION, not once per
        # session. A commit hands this connection back — NullPool closes it, a pool
        # recycles it — so anything after the first commit would otherwise run with
        # search_path = public, and a pooled connection could arrive still carrying
        # ANOTHER tenant's search_path. A commit cannot undo a per-BEGIN SET LOCAL.
        from app.database import bind_tenant_search_path
        bind_tenant_search_path(_async_engine)
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


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    base=VidyaTask,
    name="app.workers.heavy.detect_scan_quality",
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def detect_scan_quality(
    *,
    job_id: str,
    script_id: str,
    schema_name: str,
    **kwargs,
) -> dict:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Which tenant every transaction in this task belongs to. Held for the whole
    # run and dropped at the end of it: a worker process is long-lived and serves
    # every tenant in turn, and a schema left set is one the next task inherits.
    with tenant_schema_scope(schema_name):
        return asyncio.run(
            _run_quality_check(
                job_id=job_id,
                script_id=script_id,
                schema_name=schema_name,
            )
        )


# ---------------------------------------------------------------------------
# Inner async implementation
# ---------------------------------------------------------------------------

async def _run_quality_check(*, job_id: str, script_id: str, schema_name: str) -> dict:
    from uuid import UUID
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.audit_log.models import AuditEventType
    from app.core.audit_log.service import AuditService
    from app.modules.m09_paper_admin.models import ScriptStatus
    from app.modules.m09_paper_admin.repository import ScriptRepository
    from app.modules.m09_paper_admin.scan_quality_detector import detect_scan_quality as _detect

    engine = _get_async_engine()
    script_uuid = UUID(script_id)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        # 1. Load script
        script = await ScriptRepository.get_by_id(script_uuid, db=session)
        if script is None:
            raise ValueError(
                f"ScannedScript {script_id} not found in schema {schema_name!r}."
            )

        # 2. Mark as quality-checking in progress
        await ScriptRepository.set_quality_checking(script_uuid, db=session)
        await session.commit()

        await AuditService.log(
            AuditEventType.SCRIPT_QUALITY_CHECK_STARTED,
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
                    "script=%s has no upload_url — quality check will flag PARTIAL_SCAN.",
                    script_id,
                )
                pdf_bytes = b""

            # 4. Detect quality (never raises)
            result = _detect(
                pdf_bytes,
                expected_page_count=script.page_count,
            )

            # 5. Persist results + advance status
            flags_json = [f.to_dict() for f in result.flags]
            await ScriptRepository.set_quality_result(
                script_uuid,
                quality_score=result.quality_score,
                flags=flags_json,
                passed=result.passed,
                db=session,
            )
            await session.commit()

            # 6. Audit
            new_status = (
                ScriptStatus.OCR_PROCESSING.value
                if result.passed
                else ScriptStatus.QUALITY_FAILED.value
            )
            audit_event = (
                AuditEventType.SCRIPT_QUALITY_CHECK_COMPLETED
                if result.passed
                else AuditEventType.SCRIPT_QUALITY_CHECK_FAILED
            )
            await AuditService.log(
                audit_event,
                actor_user_id=None,
                actor_role="SYSTEM",
                tenant_id=None,
                schema_name=schema_name,
                target_entity="scanned_script",
                target_id=script_id,
                metadata={
                    "quality_score": result.quality_score,
                    "flag_count":    len(result.flags),
                    "passed":        result.passed,
                    "page_count":    result.page_count,
                    "final_status":  new_status,
                },
            )

            # 6b. Chain to OCR task when quality passed
            if result.passed:
                from app.workers.heavy.ocr_scanned_script import ocr_scanned_script
                ocr_scanned_script.apply_async(
                    kwargs={
                        "job_id":      job_id,
                        "script_id":   script_id,
                        "schema_name": schema_name,
                    },
                    queue="celery-heavy",
                )
                logger.info(
                    "Quality passed — dispatched OCR task for script=%s", script_id
                )

            logger.info(
                "Quality check complete: script=%s score=%.1f passed=%s flags=%d status=%s",
                script_id, result.quality_score, result.passed, len(result.flags), new_status,
            )

            return {
                "script_id":     script_id,
                "quality_score": result.quality_score,
                "flag_count":    len(result.flags),
                "passed":        result.passed,
                "status":        new_status,
            }

        except Exception as exc:
            logger.error(
                "Quality check failed for script=%s: %s", script_id, exc, exc_info=True,
            )
            try:
                await ScriptRepository.set_failed(script_uuid, db=session)
                await session.commit()
            except Exception:
                pass
            try:
                await AuditService.log(
                    AuditEventType.SCRIPT_QUALITY_CHECK_FAILED,
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
