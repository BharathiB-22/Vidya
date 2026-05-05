import logging
import time
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.core.auth.router import limiter as auth_limiter
from app.core.auth.router import router as auth_router
from app.core.auth.platform_router import router as platform_router
from app.core.auth.admin_router import router as admin_router

logger = logging.getLogger("vidya.access")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Vidya Backend")

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
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logger
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info("%s %s %d %.1fms", request.method, request.url.path, response.status_code, duration_ms)
    return response


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

app.include_router(auth_router, prefix="/auth")
app.include_router(platform_router, prefix="/platform/auth")
app.include_router(admin_router, prefix="/admin")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok", "environment": settings.ENVIRONMENT}
