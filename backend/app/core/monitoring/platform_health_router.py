import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.database import get_db
from app.core.auth.dependencies import require_super_admin
from app.core.auth.schemas import CurrentUser
from app.core.monitoring.health import HealthCheckResult, HealthService
from app.core.monitoring.schemas import (
    AIProviderDiagnostic,
    PlatformDiagnosticService,
    PlatformHealthResponse,
    QueueDiagnostics,
)

router = APIRouter(tags=["platform-health"])

_LABELS: dict[str, str] = {
    "db":           "PostgreSQL",
    "redis":        "Redis",
    "s3":           "MinIO / S3",
    "qdrant":       "Qdrant Vector DB",
    "api":          "API Server",
    "celery":       "Celery Worker",
    "celery-heavy": "Celery Heavy Worker",
}


def _to_diag(r: HealthCheckResult) -> PlatformDiagnosticService:
    return PlatformDiagnosticService(
        service=r.service,
        label=_LABELS.get(r.service, r.service),
        status=r.status,
        latency_ms=round(r.latency_ms, 1),
        detail=r.detail,
        error_msg=r.error_msg,
    )


@router.get("", response_model=PlatformHealthResponse)
async def get_platform_health(
    _: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> PlatformHealthResponse:
    # 1. System + worker checks in parallel
    (system_results, all_sys_healthy), (worker_results, workers_online) = await asyncio.gather(
        HealthService.check_all(),
        HealthService.check_celery_workers(),
    )

    # API server is always responding if this code runs
    api_result = HealthCheckResult("api", "healthy", 0.0, detail="Responding")

    system  = [_to_diag(r) for r in [*system_results, api_result]]
    workers = [_to_diag(r) for r in worker_results]

    # 2. Queue statistics (single query using task_jobs)
    qrow = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE status = 'PENDING')                                         AS pending,
            COUNT(*) FILTER (WHERE status = 'RUNNING')                                         AS running,
            COUNT(*) FILTER (WHERE status = 'SUCCESS')                                         AS completed,
            COUNT(*) FILTER (WHERE status IN ('FAILED', 'CANCELLED'))                          AS failed,
            COUNT(*) FILTER (WHERE status = 'FAILED'
                              AND created_at >= NOW() - INTERVAL '24 hours')                   AS failed_24h,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours')                  AS total_24h,
            COUNT(*) FILTER (WHERE status = 'PENDING'  AND queue_name = 'celery')              AS celery_pending,
            COUNT(*) FILTER (WHERE status = 'RUNNING'  AND queue_name = 'celery')              AS celery_running,
            COUNT(*) FILTER (WHERE status = 'PENDING'  AND queue_name = 'celery-heavy')        AS heavy_pending,
            COUNT(*) FILTER (WHERE status = 'RUNNING'  AND queue_name = 'celery-heavy')        AS heavy_running
        FROM public.task_jobs
    """))
    qc = qrow.one()

    queue = QueueDiagnostics(
        pending=qc.pending or 0,
        running=qc.running or 0,
        completed=qc.completed or 0,
        failed=qc.failed or 0,
        failed_24h=qc.failed_24h or 0,
        total_24h=qc.total_24h or 0,
        celery_pending=qc.celery_pending or 0,
        celery_running=qc.celery_running or 0,
        heavy_pending=qc.heavy_pending or 0,
        heavy_running=qc.heavy_running or 0,
        workers_online=workers_online,
    )

    # 3. AI provider diagnostics (config-level, no live API calls)
    active = app_settings.AI_PROVIDER
    ai = [
        AIProviderDiagnostic(
            name="Gemini",
            provider_key="gemini",
            active=(active in ("gemini", "fallback")),
            configured=bool(app_settings.GEMINI_API_KEY),
            model=app_settings.GEMINI_MODEL,
            status="ready" if bool(app_settings.GEMINI_API_KEY) else "not_configured",
        ),
        AIProviderDiagnostic(
            name="Groq",
            provider_key="groq",
            active=(active in ("groq", "fallback")),
            configured=bool(app_settings.GROQ_API_KEY),
            model=app_settings.GROQ_MODEL,
            status="ready" if bool(app_settings.GROQ_API_KEY) else "not_configured",
        ),
    ]

    # 4. Overall health — system must be healthy; worker warnings are non-critical
    all_healthy = all_sys_healthy

    return PlatformHealthResponse(
        generated_at=datetime.now(timezone.utc),
        all_healthy=all_healthy,
        system=system,
        workers=workers,
        queue=queue,
        ai=ai,
    )
