import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.config import settings
from app.core.monitoring import setup_logging
from app.core.monitoring.middleware import MonitoringMiddleware
from app.core.monitoring.router import router as monitoring_router
from app.core.rate_limiting import limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.auth.router import router as auth_router
from app.core.auth.platform_router import router as platform_router
from app.core.auth.admin_router import router as admin_router
from app.core.onboarding.router import router as onboarding_router
from app.core.tenants.router import router as tenants_router
from app.core.audit_log.router import router as audit_log_router
from app.core.audit_log.platform_router import router as platform_audit_router
from app.core.monitoring.platform_health_router import router as platform_health_router
from app.core.notifications.router import router as notifications_router
from app.core.storage.router import router as storage_router
from app.core.storage.provisioner import ensure_bucket_exists
from app.modules.m01_program_advisor.router import router as program_router
from app.modules.m02_syllabus.router import router as syllabus_router
from app.modules.m03_course_kit.router import router as course_kit_router
from app.modules.m05_learning_materials.router import router as learning_router
from app.modules.m06_labs_evaluator.router import router as labs_router
from app.modules.m07_research_supervision.router import router as research_router
from app.modules.m08_exam_setter.router import router as exam_router
from app.modules.m09_paper_admin.router import router as paper_admin_router
from app.modules.m09_paper_admin.assignment_router import router as evaluation_assignment_router
from app.modules.m09_paper_admin.analytics_router import router as exam_analytics_router
from app.modules.m10_bell_curve.router import router as bell_curve_router
from app.modules.m_academics.router import router as academics_router
from app.modules.m_academics.assignment_router import router as assignment_router
from app.modules.m11_sis.router import router as sis_router
from app.modules.m11_sis.transcript_router import verify_router
from app.modules.m11_sis.graduation_router import cert_verify_router

setup_logging(log_level=settings.LOG_LEVEL, json_logging=settings.JSON_LOGGING)
logger = logging.getLogger("vidya.access")

_is_prod = settings.ENVIRONMENT == "production"

app = FastAPI(
    title="Vidya Backend",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Initialize storage bucket on app startup."""
    try:
        await ensure_bucket_exists()
    except Exception as e:
        logger.warning("Storage bucket unavailable at startup (MinIO not running?): %s", e)


# ---------------------------------------------------------------------------
# slowapi rate limiter
# ---------------------------------------------------------------------------

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "RATE_LIMITED", "message": "Too many requests"},
    )


# ---------------------------------------------------------------------------
# Middleware stack  (add_middleware is LIFO — last added runs first on request)
#
# Request path:  ProxyHeaders → CORS → Monitoring → SlowAPI → SecurityHeaders → app
# Response path: app → SecurityHeaders → SlowAPI → Monitoring → CORS → ProxyHeaders
#
# ProxyHeaders outermost: fixes client IP from X-Forwarded-For before SlowAPI reads it.
# CORS before SlowAPI: OPTIONS preflights are answered without consuming rate-limit quota.
# SecurityHeaders innermost: injects headers into every response from the app.
# ---------------------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(MonitoringMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Tenant-Slug", "X-Request-ID"],
)

app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=settings.TRUSTED_PROXY_IPS,
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        content = exc.detail
    else:
        content = {"error": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(monitoring_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(platform_router, prefix="/platform/auth")
app.include_router(admin_router, prefix="/admin")
app.include_router(onboarding_router, prefix="/admin/onboarding")
app.include_router(tenants_router, prefix="/tenants")
app.include_router(audit_log_router, prefix="/audit-logs")
app.include_router(platform_audit_router,  prefix="/platform/audit-logs")
app.include_router(platform_health_router, prefix="/platform/health")
app.include_router(notifications_router, prefix="/notifications")
app.include_router(storage_router, prefix="/storage")
app.include_router(program_router, prefix="/programs")
app.include_router(syllabus_router, prefix="/syllabi")
app.include_router(course_kit_router, prefix="/course-kits")
app.include_router(learning_router, prefix="/learning-packages")
app.include_router(labs_router, prefix="/labs")
app.include_router(research_router, prefix="/research")
app.include_router(exam_router,        prefix="/exams")
app.include_router(paper_admin_router, prefix="/scripts")
app.include_router(evaluation_assignment_router, prefix="/evaluation-assignments")
app.include_router(exam_analytics_router, prefix="/exam-analytics")
app.include_router(bell_curve_router, prefix="/bell-curve")
app.include_router(academics_router,  prefix="/academics")
app.include_router(assignment_router, prefix="/course-assignments")
app.include_router(sis_router,          prefix="/sis")
app.include_router(verify_router,       prefix="/verify")
app.include_router(cert_verify_router)
