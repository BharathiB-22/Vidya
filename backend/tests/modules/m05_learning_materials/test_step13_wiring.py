"""
STEP-13 wiring verification tests for M05 Learning Material Packager.

Checks (no live services needed):
  1. All M05 modules import without errors
  2. Config has all required M05 keys with correct types
  3. Both M05 Celery tasks are in celery_app.conf.include
  4. Router is mounted at /learning-packages in the FastAPI app
  5. All M05 AuditEventType values are defined
  6. Key M05 endpoints appear in the OpenAPI route table
"""
from __future__ import annotations


# ===========================================================================
# 1. Module imports
# ===========================================================================

def test_models_import():
    from app.modules.m05_learning_materials import models  # noqa: F401
    assert hasattr(models, "LearningPackage")
    assert hasattr(models, "PackageItem")
    assert hasattr(models, "PackageQASession")
    assert hasattr(models, "PackageQAMessage")


def test_schemas_import():
    from app.modules.m05_learning_materials import schemas  # noqa: F401
    assert hasattr(schemas, "CurationTriggerRequest")
    assert hasattr(schemas, "CurationJobResponse")
    assert hasattr(schemas, "LearningPackageResponse")
    assert hasattr(schemas, "PackageItemResponse")
    assert hasattr(schemas, "RAGAnswerResponse")


def test_repository_import():
    from app.modules.m05_learning_materials import repository  # noqa: F401
    assert hasattr(repository, "LearningPackageRepository")
    assert hasattr(repository, "PackageItemRepository")
    assert hasattr(repository, "PackageQARepository")


def test_service_import():
    from app.modules.m05_learning_materials import service  # noqa: F401
    assert hasattr(service, "LearningPackageService")
    assert hasattr(service, "PackageServiceError")


def test_router_import():
    from app.modules.m05_learning_materials import router  # noqa: F401
    assert hasattr(router, "router")


def test_embedder_import():
    from app.modules.m05_learning_materials import embedder  # noqa: F401
    assert hasattr(embedder, "embed_texts")
    assert hasattr(embedder, "score_items")


def test_rag_service_import():
    from app.modules.m05_learning_materials import rag_service  # noqa: F401
    assert hasattr(rag_service, "ask_package_question")
    assert hasattr(rag_service, "RagServiceError")


def test_source_adapters_import():
    from app.modules.m05_learning_materials.source_adapters import base
    from app.modules.m05_learning_materials.source_adapters import youtube
    from app.modules.m05_learning_materials.source_adapters import arxiv
    from app.modules.m05_learning_materials.source_adapters import nptel
    from app.modules.m05_learning_materials.source_adapters import mit_ocw
    assert hasattr(base, "AbstractSourceAdapter")
    assert hasattr(base, "RawItem")
    assert hasattr(youtube, "YouTubeAdapter")
    assert hasattr(arxiv, "ArxivAdapter")
    assert hasattr(nptel, "NptelAdapter")
    assert hasattr(mit_ocw, "MitOcwAdapter")


def test_curate_task_import():
    from app.workers.heavy.curate_learning_package import curate_learning_package
    assert callable(curate_learning_package)


def test_index_rag_task_import():
    from app.workers.heavy.index_package_rag import index_package_rag
    assert callable(index_package_rag)


# ===========================================================================
# 2. Config keys
# ===========================================================================

def test_config_has_m05_keys():
    from app.config import settings

    assert isinstance(settings.YOUTUBE_API_KEY, str)
    assert isinstance(settings.QDRANT_URL, str)
    assert settings.QDRANT_URL.startswith("http")
    assert isinstance(settings.QDRANT_API_KEY, str)
    assert isinstance(settings.M05_TOP_N_PER_UNIT, int)
    assert settings.M05_TOP_N_PER_UNIT > 0
    assert isinstance(settings.M05_EMBED_BATCH_SIZE, int)
    assert settings.M05_EMBED_BATCH_SIZE > 0
    assert isinstance(settings.M05_RAG_TOP_K, int)
    assert settings.M05_RAG_TOP_K > 0
    assert isinstance(settings.M05_RAG_CHUNK_TOKENS, int)
    assert settings.M05_RAG_CHUNK_TOKENS > 0
    assert isinstance(settings.M05_RAG_CHUNK_OVERLAP, int)
    assert settings.M05_RAG_CHUNK_OVERLAP < settings.M05_RAG_CHUNK_TOKENS


# ===========================================================================
# 3. Celery task registration
# ===========================================================================

def test_celery_includes_m05_tasks():
    from app.workers.celery_app import celery_app

    include = celery_app.conf.include
    assert "app.workers.heavy.curate_learning_package" in include, (
        "curate_learning_package not in Celery include list"
    )
    assert "app.workers.heavy.index_package_rag" in include, (
        "index_package_rag not in Celery include list"
    )


# ===========================================================================
# 4. Router mount in FastAPI app
# ===========================================================================

def test_learning_packages_router_is_mounted():
    from app.main import app

    routes = [getattr(r, "path", "") for r in app.routes]
    # The prefix /learning-packages should appear in at least one route path.
    m05_routes = [p for p in routes if p.startswith("/learning-packages")]
    assert len(m05_routes) > 0, (
        f"/learning-packages prefix not found in app routes. Found: {routes}"
    )


def test_key_endpoints_registered():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    expected = [
        "/learning-packages/curate",
        "/learning-packages/jobs/{job_id}",
        "/learning-packages",
        "/learning-packages/{package_id}",
        "/learning-packages/{package_id}/items",
        "/learning-packages/{package_id}/ask",
    ]
    for path in expected:
        assert path in paths, f"Expected route '{path}' not found in app routes"


# ===========================================================================
# 5. Audit event types
# ===========================================================================

def test_m05_audit_event_types_defined():
    from app.core.audit_log.models import AuditEventType

    expected = [
        "LEARNING_PACKAGE_CURATION_QUEUED",
        "LEARNING_PACKAGE_CURATION_COMPLETED",
        "LEARNING_PACKAGE_CURATION_FAILED",
        "LEARNING_PACKAGE_RAG_INDEXING_COMPLETED",
        "LEARNING_PACKAGE_RAG_INDEXING_FAILED",
        "LEARNING_PACKAGE_ITEM_ADDED",
        "LEARNING_PACKAGE_ITEM_REMOVED",
        "LEARNING_PACKAGE_ITEM_RECOMMENDATION_TOGGLED",
    ]
    defined = {e.value for e in AuditEventType}
    for name in expected:
        assert name in defined, f"AuditEventType.{name} not defined"


# ===========================================================================
# 6. qdrant-client package is available
# ===========================================================================

def test_qdrant_client_installed():
    # importlib.metadata is immune to conftest sys.modules stubs.
    from importlib.metadata import version, PackageNotFoundError
    try:
        ver = version("qdrant-client")
    except PackageNotFoundError:
        raise AssertionError(
            "qdrant-client is not installed. Run: pip install qdrant-client>=1.9"
        )
    major, minor, *_ = ver.split(".")
    assert int(major) >= 1 and int(minor) >= 9 or int(major) > 1, (
        f"qdrant-client {ver} is too old; need >=1.9"
    )


def test_tenacity_installed():
    from importlib.metadata import version, PackageNotFoundError
    try:
        ver = version("tenacity")
    except PackageNotFoundError:
        raise AssertionError(
            "tenacity is not installed. Run: pip install tenacity>=8.2"
        )
    major, *_ = ver.split(".")
    assert int(major) >= 8, f"tenacity {ver} is too old; need >=8.2"
