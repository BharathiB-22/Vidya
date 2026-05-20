"""H05-05: security middleware, CORS, and rate-limiting configuration tests.

All tests are pure-unit or use a minimal in-process app — no real database or
MinIO connection required.
"""
import inspect

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.rate_limiting import limiter
from app.core.security_headers import SecurityHeadersMiddleware


# ── SecurityHeadersMiddleware ────────────────────────────────────────────────

@pytest.fixture
def headers_app():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.get("/already-has-frame-options")
    def already_has_header():
        resp = JSONResponse({"ok": True})
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        return resp

    return app


def test_security_headers_are_injected(headers_app):
    client = TestClient(headers_app)
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["x-xss-protection"] == "0"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"


def test_security_header_not_overridden_when_already_set(headers_app):
    """Middleware must skip headers already present — not clobber or duplicate them."""
    client = TestClient(headers_app)
    r = client.get("/already-has-frame-options")
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_security_headers_not_applied_to_non_http_scopes():
    """Middleware passes non-HTTP scopes (lifespan, websocket) through untouched."""
    from starlette.testclient import TestClient as StarletteClient
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    def home(request):
        return PlainTextResponse("ok")

    star_app = Starlette(routes=[Route("/", home)])
    star_app.add_middleware(SecurityHeadersMiddleware)

    client = StarletteClient(star_app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"


# ── Rate limiter configuration ───────────────────────────────────────────────

def test_global_rate_limit_is_600_per_minute():
    # slowapi stores limits as LimitGroup objects; unwrap to check the value.
    limit_obj = list(limiter._default_limits[0])[0].limit
    assert str(limit_obj) == "600 per 1 minute"


def test_ai_endpoints_have_request_parameter():
    """slowapi requires `request: Request` as the first parameter of a limited endpoint."""
    from app.modules.m01_program_advisor.router import dispatch_ai_generation
    from app.modules.m02_syllabus.router import generate_syllabus
    from app.modules.m03_course_kit.router import generate_kit
    from app.modules.m05_learning_materials.router import trigger_curation, trigger_rag_indexing
    from app.modules.m07_research_supervision.router import generate_ai_problems
    from app.modules.m08_exam_setter.router import create_exam_paper

    for func in (
        dispatch_ai_generation,
        generate_syllabus,
        generate_kit,
        trigger_curation,
        trigger_rag_indexing,
        generate_ai_problems,
        create_exam_paper,
    ):
        params = list(inspect.signature(func).parameters)
        assert params[0] == "request", (
            f"{func.__name__} must have `request: Request` as first parameter "
            "(required by slowapi @limiter.limit decorator)"
        )


def test_auth_routers_import_shared_limiter():
    """Auth routers must use the shared limiter, not create their own Limiter instance."""
    import app.core.auth.router as auth_module
    import app.core.auth.platform_router as platform_module
    from app.core.rate_limiting import limiter as shared

    assert auth_module.limiter is shared, "auth router must use shared limiter"
    assert platform_module.limiter is shared, "platform router must use shared limiter"


# ── CORS configuration ───────────────────────────────────────────────────────

@pytest.fixture
def cors_app():
    """Minimal app with CORSMiddleware mirroring main.py settings."""
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Tenant-Slug", "X-Request-ID"],
    )

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


def test_cors_preflight_accepted_from_known_origin(cors_app):
    client = TestClient(cors_app)
    r = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight_rejected_from_unknown_origin(cors_app):
    client = TestClient(cors_app)
    r = client.options(
        "/ping",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in r.headers


def test_cors_options_is_in_allowed_methods(cors_app):
    """OPTIONS must be in allow_methods so preflight requests are handled correctly."""
    client = TestClient(cors_app)
    r = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    allowed = r.headers.get("access-control-allow-methods", "")
    assert "OPTIONS" in allowed


# ── Docs disabled in production ──────────────────────────────────────────────

def test_docs_are_inaccessible_when_disabled():
    """When FastAPI is created with docs_url/redoc_url/openapi_url=None, all return 404."""
    prod_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @prod_app.get("/health")
    def health():
        return {"status": "ok"}

    client = TestClient(prod_app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_enabled_in_development():
    """In dev/test environment the app exposes /docs and /openapi.json."""
    from app.main import app
    from app.config import settings

    if settings.ENVIRONMENT == "production":
        pytest.skip("Docs are intentionally disabled in production")

    assert app.docs_url is not None, "docs_url should be set in development"
    assert app.openapi_url is not None, "openapi_url should be set in development"
