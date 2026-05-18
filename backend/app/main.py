import logging
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.monitoring import setup_logging
from app.core.monitoring.middleware import MonitoringMiddleware
from app.core.monitoring.router import router as monitoring_router
from app.core.auth.router import limiter as auth_limiter
from app.core.auth.router import router as auth_router
from app.core.auth.platform_router import router as platform_router
from app.core.auth.admin_router import router as admin_router
from app.core.tenants.router import router as tenants_router
from app.core.audit_log.router import router as audit_log_router
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

setup_logging(log_level=settings.LOG_LEVEL, json_logging=settings.JSON_LOGGING)
logger = logging.getLogger("vidya.access")

app = FastAPI(title="Vidya Backend")


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

app.state.limiter = auth_limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "RATE_LIMITED", "message": "Too many requests"},
    )


# ---------------------------------------------------------------------------
# Middleware stack
# ---------------------------------------------------------------------------

app.add_middleware(MonitoringMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    message = traceback.format_exc() if settings.ENVIRONMENT == "development" else "An unexpected error occurred"
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": message},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(monitoring_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(platform_router, prefix="/platform/auth")
app.include_router(admin_router, prefix="/admin")
app.include_router(tenants_router, prefix="/tenants")
app.include_router(audit_log_router, prefix="/audit-logs")
app.include_router(notifications_router, prefix="/notifications")
app.include_router(storage_router, prefix="/storage")
app.include_router(program_router, prefix="/programs")
app.include_router(syllabus_router, prefix="/syllabi")
app.include_router(course_kit_router, prefix="/course-kits")
app.include_router(learning_router, prefix="/learning-packages")
app.include_router(labs_router, prefix="/labs")
app.include_router(research_router, prefix="/research")
app.include_router(exam_router,     prefix="/exams")
