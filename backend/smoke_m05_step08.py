"""STEP-08 smoke tests -- M05 curation Celery task.

Inspect-based + mock-based: verifies task structure, partial-failure tolerance,
full-pipeline happy path, and status lifecycle. No real DB or network.

Patching note: _run_curation uses deferred imports (inside the function body).
We therefore patch at the SOURCE module paths, not at the worker module path.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import asyncio
import os

os.environ.setdefault("DATABASE_URL",   "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("REDIS_URL",      "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET",     "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("YOUTUBE_API_KEY","test-yt-key")

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {label}")
        PASS += 1
    else:
        print(f"  [FAIL] {label}")
        FAIL += 1


# ===========================================================================
# 1. Import contract
# ===========================================================================
print("\n--- imports ---")

from app.workers.heavy.curate_learning_package import (
    curate_learning_package,
    _run_curation,
    _content_hash,
)

check("curate_learning_package task importable", callable(curate_learning_package))
check("_run_curation is a coroutine function",  inspect.iscoroutinefunction(_run_curation))
check("_content_hash is callable",              callable(_content_hash))

# ===========================================================================
# 2. Task registration
# ===========================================================================
print("\n--- task registration ---")

from app.workers.celery_app import celery_app

check(
    "task registered as app.workers.heavy.curate_learning_package",
    "app.workers.heavy.curate_learning_package" in celery_app.tasks,
)

# ===========================================================================
# 3. AuditEventType entries exist
# ===========================================================================
print("\n--- audit event types ---")

from app.core.audit_log.models import AuditEventType

check(
    "LEARNING_PACKAGE_CURATION_QUEUED exists",
    hasattr(AuditEventType, "LEARNING_PACKAGE_CURATION_QUEUED"),
)
check(
    "LEARNING_PACKAGE_CURATION_COMPLETED exists",
    hasattr(AuditEventType, "LEARNING_PACKAGE_CURATION_COMPLETED"),
)
check(
    "LEARNING_PACKAGE_CURATION_FAILED exists",
    hasattr(AuditEventType, "LEARNING_PACKAGE_CURATION_FAILED"),
)

# ===========================================================================
# 4. _content_hash helper
# ===========================================================================
print("\n--- _content_hash ---")

from app.modules.m05_learning_materials.source_adapters.base import RawItem

item_with_url   = RawItem(source_type="YOUTUBE", title="Intro ML", url="https://yt.com/1", raw_text="x")
item_no_url     = RawItem(source_type="ARXIV",   title="ML Paper", url=None, raw_text="x")
item_empty      = RawItem(source_type="NPTEL",   title="",         url=None, raw_text="x")
item_whitespace = RawItem(source_type="NPTEL",   title="  ",       url="  ", raw_text="x")

check("_content_hash returns str for item with url",   isinstance(_content_hash(item_with_url), str))
check("_content_hash returns 64-char hex",             len(_content_hash(item_with_url)) == 64)
check("_content_hash is deterministic",
      _content_hash(item_with_url) == _content_hash(item_with_url))
check("_content_hash differs for different items",
      _content_hash(item_with_url) != _content_hash(item_no_url))
check("_content_hash works without url (uses title)",  isinstance(_content_hash(item_no_url), str))
check("_content_hash returns None for empty url+title", _content_hash(item_empty) is None)
check("_content_hash treats whitespace-only as None",  _content_hash(item_whitespace) is None)

# ===========================================================================
# 5. Helpers
# ===========================================================================

def _make_unit(title="ML Fundamentals", unit_number=1, topics=None):
    unit = MagicMock()
    unit.title = title
    unit.unit_number = unit_number
    unit.topics = topics or [{"title": "Neural Networks"}, {"title": "Backprop"}]
    return unit


def _make_package(status_val="PENDING", top_n=5):
    from app.modules.m05_learning_materials.models import PackageStatus
    pkg = MagicMock()
    pkg.status = PackageStatus(status_val)
    pkg.top_n = top_n
    return pkg


def _raw(title: str, url: str | None = None) -> RawItem:
    return RawItem(source_type="YOUTUBE", title=title, url=url, raw_text=f"text {title}")


def _make_mock_session() -> AsyncMock:
    """Return an async-context-manager-compatible mock session."""
    sess = AsyncMock()
    sess.execute = AsyncMock()
    sess.flush   = AsyncMock()
    sess.commit  = AsyncMock()
    sess.__aenter__ = AsyncMock(return_value=sess)
    sess.__aexit__  = AsyncMock(return_value=False)
    return sess


def _session_factory(mock_sess):
    """Return a fake AsyncSession class whose instances behave as mock_sess."""
    class _FakeAsyncSession:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return mock_sess
        async def __aexit__(self, *args):
            return False
    return _FakeAsyncSession


# Source module patch paths (all deferred inside _run_curation)
_AUDIT_SVC  = "app.core.audit_log.service.AuditService"
_UNIT_REPO  = "app.modules.m02_syllabus.repository.SyllabusUnitRepository"
_LP_REPO    = "app.modules.m05_learning_materials.repository.LearningPackageRepository"
_PI_REPO    = "app.modules.m05_learning_materials.repository.PackageItemRepository"
_YT_ADAPT   = "app.modules.m05_learning_materials.source_adapters.YouTubeAdapter"
_AX_ADAPT   = "app.modules.m05_learning_materials.source_adapters.ArxivAdapter"
_NP_ADAPT   = "app.modules.m05_learning_materials.source_adapters.NptelAdapter"
_OC_ADAPT   = "app.modules.m05_learning_materials.source_adapters.MitOcwAdapter"
_SCORE      = "app.modules.m05_learning_materials.embedder.score_items"
_ASYNC_SESS = "sqlalchemy.ext.asyncio.AsyncSession"

from uuid import uuid4

_pkg_id     = uuid4()
_tenant_id  = uuid4()
_syllabus_id = uuid4()

# ===========================================================================
# 6. Happy path: all 4 adapters return items, ranked, persisted
# ===========================================================================
print("\n--- happy path: all adapters succeed ---")

items_yt = [_raw("YT A", "https://yt.com/a"), _raw("YT B", "https://yt.com/b")]
items_ax = [_raw("Arxiv C", "https://arxiv.org/c")]
items_np = [_raw("NPTEL D")]
items_oc = [_raw("MIT E", "https://ocw.mit.edu/e")]
all_items = items_yt + items_ax + items_np + items_oc  # 5 items

pkg = _make_package(status_val="PENDING", top_n=3)
unit = _make_unit()

ranked_output = [(item, 0.9 - i * 0.1) for i, item in enumerate(all_items)]

created_items = [MagicMock() for _ in range(3)]  # top_n=3

mock_sess = _make_mock_session()

with (
    patch(_ASYNC_SESS, _session_factory(mock_sess)),
    patch(_AUDIT_SVC) as mock_audit,
    patch(_UNIT_REPO) as mock_unit_repo,
    patch(_LP_REPO)   as mock_lp_repo,
    patch(_PI_REPO)   as mock_pi_repo,
    patch(_YT_ADAPT)  as mock_yt,
    patch(_AX_ADAPT)  as mock_ax,
    patch(_NP_ADAPT)  as mock_np,
    patch(_OC_ADAPT)  as mock_oc,
    patch(_SCORE, new=AsyncMock(return_value=ranked_output)) as mock_score,
):
    mock_lp_repo.get_by_id    = AsyncMock(return_value=pkg)
    mock_lp_repo.set_curating = AsyncMock(return_value=pkg)
    mock_lp_repo.set_ready    = AsyncMock(return_value=pkg)
    mock_lp_repo.update_status = AsyncMock(return_value=pkg)

    mock_unit_repo.get_by_number = AsyncMock(return_value=unit)

    mock_pi_repo.delete_all_for_package = AsyncMock(return_value=0)
    mock_pi_repo.bulk_create            = AsyncMock(return_value=created_items)

    mock_audit.log = AsyncMock()

    for items, mock_cls in [
        (items_yt, mock_yt), (items_ax, mock_ax),
        (items_np, mock_np), (items_oc, mock_oc),
    ]:
        inst = AsyncMock()
        inst.search = AsyncMock(return_value=items)
        mock_cls.return_value = inst

    result = asyncio.run(
        _run_curation(
            package_id=_pkg_id,
            tenant_id=_tenant_id,
            tenant_schema="tenant_test",
            syllabus_id=_syllabus_id,
            unit_number=1,
            top_n=3,
        )
    )

check("happy path: returns dict",            isinstance(result, dict))
check("happy path: package_id in result",    str(_pkg_id) == result.get("package_id"))
check("happy path: items_created=3 (top_n)", result.get("items_created") == 3)
check("happy path: no failed_providers",     result.get("failed_providers") == [])
check("happy path: score_items called once", mock_score.call_count == 1)
check("happy path: bulk_create called once", mock_pi_repo.bulk_create.call_count == 1)
check("happy path: set_curating called",     mock_lp_repo.set_curating.call_count == 1)
check("happy path: set_ready called",        mock_lp_repo.set_ready.call_count == 1)
check("happy path: audit COMPLETED called",  mock_audit.log.call_count >= 1)

# Verify bulk_create received top_n=3 items
bulk_call_args = mock_pi_repo.bulk_create.call_args
bulk_items_arg = bulk_call_args[0][1] if bulk_call_args[0] else bulk_call_args.kwargs.get("items", [])
check("happy path: bulk_create got exactly 3 items (top_n slice)", len(bulk_items_arg) == 3)

orders = [d.get("display_order") for d in bulk_items_arg]
check("happy path: display_order is [0, 1, 2]", orders == [0, 1, 2])

# ===========================================================================
# 7. Partial failure: one adapter fails, others succeed
# ===========================================================================
print("\n--- partial failure: one adapter fails ---")

from app.modules.m05_learning_materials.source_adapters.base import SourceAdapterError

items_partial = [_raw("Good A"), _raw("Good B")]
pkg2 = _make_package(status_val="PENDING", top_n=5)
unit2 = _make_unit()
ranked_partial = [(item, 0.8) for item in items_partial]
created_partial = [MagicMock(), MagicMock()]
mock_sess2 = _make_mock_session()

with (
    patch(_ASYNC_SESS, _session_factory(mock_sess2)),
    patch(_AUDIT_SVC) as mock_audit2,
    patch(_UNIT_REPO) as mock_ur2,
    patch(_LP_REPO)   as mock_lp2,
    patch(_PI_REPO)   as mock_pi2,
    patch(_YT_ADAPT)  as mock_yt2,
    patch(_AX_ADAPT)  as mock_ax2,
    patch(_NP_ADAPT)  as mock_np2,
    patch(_OC_ADAPT)  as mock_oc2,
    patch(_SCORE, new=AsyncMock(return_value=ranked_partial)),
):
    mock_lp2.get_by_id     = AsyncMock(return_value=pkg2)
    mock_lp2.set_curating  = AsyncMock(return_value=pkg2)
    mock_lp2.set_ready     = AsyncMock(return_value=pkg2)
    mock_lp2.update_status = AsyncMock(return_value=pkg2)
    mock_ur2.get_by_number = AsyncMock(return_value=unit2)
    mock_pi2.delete_all_for_package = AsyncMock(return_value=0)
    mock_pi2.bulk_create            = AsyncMock(return_value=created_partial)
    mock_audit2.log = AsyncMock()

    yt2 = AsyncMock(); yt2.search = AsyncMock(side_effect=SourceAdapterError("YT down"))
    ax2 = AsyncMock(); ax2.search = AsyncMock(return_value=items_partial)
    np2 = AsyncMock(); np2.search = AsyncMock(return_value=[])
    oc2 = AsyncMock(); oc2.search = AsyncMock(return_value=[])

    mock_yt2.return_value = yt2
    mock_ax2.return_value = ax2
    mock_np2.return_value = np2
    mock_oc2.return_value = oc2

    result2 = asyncio.run(
        _run_curation(
            package_id=_pkg_id,
            tenant_id=_tenant_id,
            tenant_schema="tenant_test",
            syllabus_id=_syllabus_id,
            unit_number=1,
            top_n=5,
        )
    )

check("partial fail: result returned (not raised)",    isinstance(result2, dict))
check("partial fail: failed_providers=['youtube']",    result2.get("failed_providers") == ["youtube"])
check("partial fail: items still created",             result2.get("items_created") == 2)
check("partial fail: set_ready still called",          mock_lp2.set_ready.call_count == 1)

# ===========================================================================
# 8. All adapters fail -> RuntimeError raised, status reset to PENDING
# ===========================================================================
print("\n--- all adapters fail -> error path ---")

pkg3 = _make_package(status_val="PENDING", top_n=5)
unit3 = _make_unit()
mock_sess3 = _make_mock_session()

with (
    patch(_ASYNC_SESS, _session_factory(mock_sess3)),
    patch(_AUDIT_SVC) as mock_audit3,
    patch(_UNIT_REPO) as mock_ur3,
    patch(_LP_REPO)   as mock_lp3,
    patch(_PI_REPO)   as mock_pi3,
    patch(_YT_ADAPT)  as mock_yt3,
    patch(_AX_ADAPT)  as mock_ax3,
    patch(_NP_ADAPT)  as mock_np3,
    patch(_OC_ADAPT)  as mock_oc3,
):
    mock_lp3.get_by_id     = AsyncMock(return_value=pkg3)
    mock_lp3.set_curating  = AsyncMock(return_value=pkg3)
    mock_lp3.update_status = AsyncMock(return_value=pkg3)
    mock_ur3.get_by_number = AsyncMock(return_value=unit3)
    mock_pi3.delete_all_for_package = AsyncMock(return_value=0)
    mock_audit3.log = AsyncMock()

    for mock_cls in [mock_yt3, mock_ax3, mock_np3, mock_oc3]:
        inst = AsyncMock()
        inst.search = AsyncMock(side_effect=SourceAdapterError("down"))
        mock_cls.return_value = inst

    raised_error = None
    try:
        asyncio.run(
            _run_curation(
                package_id=_pkg_id,
                tenant_id=_tenant_id,
                tenant_schema="tenant_test",
                syllabus_id=_syllabus_id,
                unit_number=1,
                top_n=5,
            )
        )
    except RuntimeError as exc:
        raised_error = exc

check("all fail: RuntimeError raised",           raised_error is not None)
check("all fail: error mentions 'adapter'",
      raised_error is not None and "adapter" in str(raised_error).lower())
check("all fail: update_status(PENDING) called", mock_lp3.update_status.call_count >= 1)
check("all fail: audit CURATION_FAILED called",  mock_audit3.log.call_count >= 1)
check("all fail: bulk_create NOT called",        mock_pi3.bulk_create.call_count == 0)

# ===========================================================================
# 9. Package not found -> ValueError raised, audit FAILED called
# ===========================================================================
print("\n--- package not found ---")

mock_sess4 = _make_mock_session()

with (
    patch(_ASYNC_SESS, _session_factory(mock_sess4)),
    patch(_AUDIT_SVC) as mock_audit4,
    patch(_UNIT_REPO),
    patch(_LP_REPO)   as mock_lp4,
    patch(_PI_REPO),
    patch(_YT_ADAPT), patch(_AX_ADAPT), patch(_NP_ADAPT), patch(_OC_ADAPT),
):
    mock_lp4.get_by_id     = AsyncMock(return_value=None)
    mock_lp4.update_status = AsyncMock()
    mock_audit4.log = AsyncMock()

    not_found_error = None
    try:
        asyncio.run(
            _run_curation(
                package_id=_pkg_id,
                tenant_id=_tenant_id,
                tenant_schema="tenant_test",
                syllabus_id=_syllabus_id,
                unit_number=1,
                top_n=5,
            )
        )
    except ValueError as exc:
        not_found_error = exc

check("not found: ValueError raised",   not_found_error is not None)
check("not found: audit FAILED called", mock_audit4.log.call_count >= 1)

# ===========================================================================
# 10. Already CURATING -> set_curating NOT called again (idempotent)
# ===========================================================================
print("\n--- idempotent: already CURATING ---")

pkg_cur = _make_package(status_val="CURATING", top_n=2)
unit_c = _make_unit()
items_c = [_raw("Item X"), _raw("Item Y")]
ranked_c = [(i, 0.7) for i in items_c]
created_c = [MagicMock(), MagicMock()]
mock_sess5 = _make_mock_session()

with (
    patch(_ASYNC_SESS, _session_factory(mock_sess5)),
    patch(_AUDIT_SVC) as mock_audit5,
    patch(_UNIT_REPO) as mock_ur5,
    patch(_LP_REPO)   as mock_lp5,
    patch(_PI_REPO)   as mock_pi5,
    patch(_YT_ADAPT)  as mock_yt5,
    patch(_AX_ADAPT)  as mock_ax5,
    patch(_NP_ADAPT)  as mock_np5,
    patch(_OC_ADAPT)  as mock_oc5,
    patch(_SCORE, new=AsyncMock(return_value=ranked_c)),
):
    mock_lp5.get_by_id     = AsyncMock(return_value=pkg_cur)
    mock_lp5.set_curating  = AsyncMock(return_value=pkg_cur)
    mock_lp5.set_ready     = AsyncMock(return_value=pkg_cur)
    mock_lp5.update_status = AsyncMock(return_value=pkg_cur)
    mock_ur5.get_by_number = AsyncMock(return_value=unit_c)
    mock_pi5.delete_all_for_package = AsyncMock(return_value=0)
    mock_pi5.bulk_create            = AsyncMock(return_value=created_c)
    mock_audit5.log = AsyncMock()

    for mock_cls in [mock_yt5, mock_ax5, mock_np5, mock_oc5]:
        inst = AsyncMock(); inst.search = AsyncMock(return_value=items_c)
        mock_cls.return_value = inst

    asyncio.run(
        _run_curation(
            package_id=_pkg_id,
            tenant_id=_tenant_id,
            tenant_schema="tenant_test",
            syllabus_id=_syllabus_id,
            unit_number=1,
            top_n=2,
        )
    )

check("idempotent: set_curating NOT called when already CURATING",
      mock_lp5.set_curating.call_count == 0)
check("idempotent: set_ready still called",
      mock_lp5.set_ready.call_count == 1)

# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*52}")
print(f"STEP-08 smoke results: {PASS} passed, {FAIL} failed")
if FAIL:
    print("FAIL -- fix issues above before proceeding.")
    sys.exit(1)
else:
    print("ALL PASS -- STEP-08 smoke tests green.")
